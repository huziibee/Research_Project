#!/usr/bin/env python3
"""Validate the future T41 human interpretation sidecar without creating labels.

The program only validates supplied future-study files.  It never reads or
changes Pilot-120, calls a model, or evaluates a system prediction.  Its
``contract`` mode validates the committed readiness contract; ``study`` mode
is deliberately unusable until two blinded reviews and adjudication exist.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_GOLD_FIELDS = (
    "intent",
    "cpc",
    "candidate_set",
    "resolution",
    "clarification",
    "rejection",
    "silent_resolution",
)
FORBIDDEN_REVIEW_KEYS = {"system_id", "system_prediction", "prediction", "raw_output", "model_output"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_not_object:{path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"jsonl_row_not_object:{path}:{number}")
        rows.append(value)
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"output_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def validate_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if contract.get("contract_id") != "t41_interpretation_sidecar_contract_v1":
        errors.append("contract_id_invalid")
    if contract.get("status") != "READINESS_ONLY_NO_ANNOTATIONS":
        errors.append("contract_status_invalid")
    if contract.get("valid_for_official_use") is not False:
        errors.append("contract_must_be_non_official")
    boundary = contract.get("boundary") or {}
    if boundary.get("pilot120_unchanged") is not True or boundary.get("readiness_artifact_is_not_a_result") is not True:
        errors.append("pilot_boundary_invalid")
    schema = contract.get("sidecar_record_schema") or {}
    required = set(schema.get("required") or [])
    if not {"record_id", "source_lineage_id", "scenario_family_id", "gold"}.issubset(required):
        errors.append("sidecar_provenance_fields_missing")
    gold = ((contract.get("$defs") or {}).get("gold") or {})
    if not set(REQUIRED_GOLD_FIELDS).issubset(set(gold.get("required") or [])):
        errors.append("sidecar_gold_fields_missing")
    adjudication = contract.get("adjudication_contract") or {}
    if adjudication.get("required_reviewers") != 2 or adjudication.get("reviewer_assignments_must_be_distinct") is not True:
        errors.append("two_reviewer_contract_invalid")
    blinded = set(adjudication.get("reviewers_blind_to") or [])
    if {"system identity", "system predictions", "each other's labels"} - blinded:
        errors.append("reviewer_blinding_incomplete")
    coverage = ((contract.get("scoring_contract") or {}).get("claim_to_gold_coverage") or {})
    expected_claims = {
        "intent_exactness",
        "cpc_exactness_and_slot_prf",
        "candidate_set_precision_recall_f1_and_exact_set",
        "resolution_value_correctness",
        "clarification_target_and_wording_correctness",
        "rejection_target_and_wording_correctness",
        "silent_resolution_value_correctness",
    }
    if expected_claims - set(coverage):
        errors.append("claim_to_gold_coverage_incomplete")
    if "NOT_COMPUTED" not in str((contract.get("scoring_contract") or {}).get("not_computed_rule") or ""):
        errors.append("not_computed_rule_missing")
    current = contract.get("current_state") or {}
    if current.get("annotations_present") is not False or current.get("scores_present") is not False:
        errors.append("readiness_state_claims_annotations_or_scores")
    return errors


def _contains_forbidden_review_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key in FORBIDDEN_REVIEW_KEYS or _contains_forbidden_review_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden_review_key(item) for item in value)
    return False


def validate_study(
    contract: dict[str, Any],
    sidecar: list[dict[str, Any]],
    review_a: list[dict[str, Any]],
    review_b: list[dict[str, Any]],
    adjudication: list[dict[str, Any]],
) -> list[str]:
    errors = validate_contract(contract)
    # The public contract keeps reusable definitions at its top level.  Copy
    # them into the standalone row schema before validation so its local
    # ``#/$defs/...`` references remain resolvable when this validator is used
    # independently of the enclosing contract document.
    sidecar_schema = dict(contract["sidecar_record_schema"])
    sidecar_schema["$defs"] = contract["$defs"]
    validator = Draft202012Validator(sidecar_schema)
    expected_ids: list[str] = []
    for number, row in enumerate(sidecar, start=1):
        expected_ids.append(str(row.get("record_id") or ""))
        errors.extend(f"sidecar:{number}:schema:{error.message}" for error in validator.iter_errors(row))
        if row.get("annotation_status") != "adjudicated":
            errors.append(f"sidecar:{number}:not_adjudicated")
    if len(expected_ids) != len(set(expected_ids)) or not all(expected_ids):
        errors.append("sidecar_record_ids_not_unique")
    review_assignments: dict[str, dict[str, str]] = {}
    for reviewer_name, reviews in (("A", review_a), ("B", review_b)):
        observed_ids: list[str] = []
        assignments_by_record: dict[str, str] = {}
        for number, review in enumerate(reviews, start=1):
            record_id = str(review.get("record_id") or "")
            observed_ids.append(record_id)
            assignment = str(review.get("review_assignment_id") or "")
            if not assignment or record_id in assignments_by_record:
                errors.append(f"review_{reviewer_name}:{number}:assignment_invalid")
            assignments_by_record[record_id] = assignment
            if _contains_forbidden_review_key(review):
                errors.append(f"review_{reviewer_name}:{number}:system_visibility_forbidden")
            blinding = review.get("blinding") or {}
            if not all(blinding.get(key) is True for key in ("blind_to_system_identity", "blind_to_system_prediction", "blind_to_other_reviewer_labels")):
                errors.append(f"review_{reviewer_name}:{number}:blinding_invalid")
            if set(REQUIRED_GOLD_FIELDS) - set((review.get("labels") or {})):
                errors.append(f"review_{reviewer_name}:{number}:labels_incomplete")
        if observed_ids != expected_ids or len(observed_ids) != len(set(observed_ids)):
            errors.append(f"review_{reviewer_name}:record_coverage_invalid")
        review_assignments[reviewer_name] = assignments_by_record
    if set(review_assignments["A"].values()) & set(review_assignments["B"].values()):
        errors.append("review_assignments_not_distinct_between_reviewers")
    if len(adjudication) != len(expected_ids):
        errors.append("adjudication:record_coverage_invalid")
    seen_adjudications: set[str] = set()
    for number, row in enumerate(adjudication, start=1):
        record_id = str(row.get("record_id") or "")
        seen_adjudications.add(record_id)
        assignments = row.get("review_assignment_ids") or []
        expected_assignments = {
            review_assignments["A"].get(record_id),
            review_assignments["B"].get(record_id),
        }
        if (
            record_id not in expected_ids
            or not isinstance(assignments, list)
            or len(assignments) != 2
            or len(set(assignments)) != 2
            or set(assignments) != expected_assignments
        ):
            errors.append(f"adjudication:{number}:review_pair_invalid")
        if set(REQUIRED_GOLD_FIELDS) - set((row.get("field_agreement") or {})):
            errors.append(f"adjudication:{number}:field_agreement_incomplete")
        if set(REQUIRED_GOLD_FIELDS) - set((row.get("adjudicated_gold") or {})):
            errors.append(f"adjudication:{number}:gold_incomplete")
        if _contains_forbidden_review_key(row):
            errors.append(f"adjudication:{number}:system_visibility_forbidden")
    if seen_adjudications != set(expected_ids):
        errors.append("adjudication:record_ids_invalid")
    return errors


def _run_contract(args: argparse.Namespace) -> int:
    contract = _load_json(args.contract)
    errors = validate_contract(contract)
    payload = {
        "status": "T41_READINESS_CONTRACT_PASSED" if not errors else "VERIFY_FAILED",
        "contract_sha256": _sha256(args.contract),
        "errors": errors,
        "annotations_created": False,
        "scores_created": False,
    }
    _write_json(args.output, payload)
    print(json.dumps({"status": payload["status"], "errors": len(errors)}, sort_keys=True))
    return 0 if not errors else 1


def _run_study(args: argparse.Namespace) -> int:
    contract = _load_json(args.contract)
    inputs = {"sidecar": args.sidecar, "review_a": args.review_a, "review_b": args.review_b, "adjudication": args.adjudication}
    errors = validate_study(contract, *(_load_jsonl(path) for path in inputs.values()))
    payload = {
        "status": "T41_SIDECAR_VALIDATION_PASSED" if not errors else "VERIFY_FAILED",
        "input_sha256": {name: _sha256(path) for name, path in inputs.items()},
        "errors": errors,
        "scoring_status": "NOT_COMPUTED" if errors else "ELIGIBLE_FOR_SEPARATE_FROZEN_SCORER",
    }
    _write_json(args.output, payload)
    print(json.dumps({"status": payload["status"], "errors": len(errors)}, sort_keys=True))
    return 0 if not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    contract = sub.add_parser("contract")
    contract.add_argument("--contract", type=Path, required=True)
    contract.add_argument("--output", type=Path, required=True)
    contract.set_defaults(run=_run_contract)
    study = sub.add_parser("study")
    study.add_argument("--contract", type=Path, required=True)
    study.add_argument("--sidecar", type=Path, required=True)
    study.add_argument("--review-a", type=Path, required=True)
    study.add_argument("--review-b", type=Path, required=True)
    study.add_argument("--adjudication", type=Path, required=True)
    study.add_argument("--output", type=Path, required=True)
    study.set_defaults(run=_run_study)
    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
