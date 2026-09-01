#!/usr/bin/env python3
"""Validate a future, independently frozen T42 single-ambiguity study.

This CPU-only validator is a readiness safeguard.  It accepts neither the
Pilot-120 corpus nor an unfrozen scaffold as evidence, and it never runs model
inference or writes labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


REQUIRED_RECORD_FIELDS = {
    "record_id",
    "source_record_id",
    "source_corpus_id",
    "source_license_id",
    "source_lineage_id",
    "scenario_family_id",
    "source_fingerprint_sha256",
    "input_fingerprint_sha256",
    "annotation_status",
    "unresolved_ambiguity_instances",
    "secondary_ambiguity_instances",
    "eligibility_assertions",
    "adjudication",
}
REQUIRED_ASSERTIONS = {"exactly_one_unresolved_ambiguity", "exactly_one_ambiguity_type", "no_secondary_ambiguity"}
REQUIRED_COMPARATORS = {"pilot_120_v1", "t41_interpretation_sidecar", "t44_independent_confirmation"}


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


def validate_scaffold(scaffold: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if scaffold.get("manifest_id") != "t42_single_ambiguity_study_scaffold_v1":
        errors.append("manifest_id_invalid")
    if scaffold.get("status") != "READINESS_ONLY_NOT_FROZEN" or scaffold.get("valid_for_official_use") is not False:
        errors.append("readiness_status_invalid")
    boundary = scaffold.get("boundary") or {}
    if boundary.get("not_a_pilot120_subset") is not True or boundary.get("not_the_deferred_plus_80_extension") is not True:
        errors.append("study_boundary_invalid")
    if boundary.get("no_source_records_or_annotations_in_this_artifact") is not True or boundary.get("no_inference") is not True:
        errors.append("readiness_no_data_boundary_invalid")
    required = set((scaffold.get("record_contract") or {}).get("required_fields") or [])
    if REQUIRED_RECORD_FIELDS - required:
        errors.append("record_contract_fields_missing")
    if set(scaffold.get("eligibility_assertions_required") or []) != REQUIRED_ASSERTIONS:
        errors.append("eligibility_assertions_invalid")
    exclusion = scaffold.get("exclusion_ledger_contract") or {}
    if set(exclusion.get("required_comparators") or []) != REQUIRED_COMPARATORS or exclusion.get("pass_value") != "no_overlap":
        errors.append("exclusion_contract_invalid")
    frozen = scaffold.get("frozen_manifest_requirements") or {}
    if frozen.get("required_status") != "T42_STUDY_FROZEN_MANIFEST" or frozen.get("required_validation_status") != "T42_SINGLE_AMBIGUITY_ELIGIBILITY_PASSED":
        errors.append("frozen_manifest_contract_invalid")
    current = scaffold.get("current_state") or {}
    if any(current.get(key) != "NOT_COMPUTED" for key in ("source_audit", "eligibility_validation", "exclusion_ledger", "frozen_manifest", "metrics")):
        errors.append("current_state_invalid")
    return errors


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def validate_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = REQUIRED_RECORD_FIELDS - set(record)
    if missing:
        errors.append(f"missing_fields:{','.join(sorted(missing))}")
        return errors
    if record.get("source_corpus_id") == "pilot_120_v1":
        errors.append("pilot120_source_forbidden")
    for field in ("record_id", "source_record_id", "source_corpus_id", "source_license_id", "source_lineage_id", "scenario_family_id"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            errors.append(f"{field}_invalid")
    for field in ("source_fingerprint_sha256", "input_fingerprint_sha256"):
        if not _is_sha256(record.get(field)):
            errors.append(f"{field}_invalid")
    instances = record.get("unresolved_ambiguity_instances")
    if not isinstance(instances, list) or len(instances) != 1:
        errors.append("unresolved_ambiguity_instances_must_have_exactly_one")
    else:
        instance = instances[0]
        if not isinstance(instance, dict):
            errors.append("unresolved_ambiguity_instance_not_object")
        else:
            if not isinstance(instance.get("ambiguity_type"), str) or not instance["ambiguity_type"].strip():
                errors.append("ambiguity_type_not_single_nonempty_string")
            if instance.get("resolution_status") != "unresolved":
                errors.append("ambiguity_not_unresolved")
            if not isinstance(instance.get("evidence_spans"), list) or not instance["evidence_spans"]:
                errors.append("ambiguity_evidence_missing")
    if record.get("secondary_ambiguity_instances") != []:
        errors.append("secondary_ambiguity_present")
    assertions = record.get("eligibility_assertions")
    if not isinstance(assertions, dict) or any(assertions.get(key) is not True for key in REQUIRED_ASSERTIONS):
        errors.append("eligibility_assertions_not_all_true")
    adjudication = record.get("adjudication")
    if record.get("annotation_status") != "adjudicated":
        errors.append("record_not_adjudicated")
    if not isinstance(adjudication, dict) or adjudication.get("status") != "adjudicated":
        errors.append("adjudication_status_invalid")
    else:
        assignments = adjudication.get("blind_review_assignment_ids")
        if not isinstance(assignments, list) or len(assignments) != 2 or len(set(assignments)) != 2:
            errors.append("blind_review_assignments_invalid")
    return errors


def validate_freeze(
    scaffold: dict[str, Any], records: list[dict[str, Any]], ledger: list[dict[str, Any]], manifest: dict[str, Any], records_path: Path, ledger_path: Path
) -> list[str]:
    errors = validate_scaffold(scaffold)
    expected_ids: list[str] = []
    for number, record in enumerate(records, start=1):
        expected_ids.append(str(record.get("record_id") or ""))
        errors.extend(f"record:{number}:{error}" for error in validate_record(record))
    if not records:
        errors.append("records_empty")
    if len(expected_ids) != len(set(expected_ids)) or not all(expected_ids):
        errors.append("record_ids_not_unique")
    ledger_by_id = {str(row.get("record_id") or ""): row for row in ledger}
    if len(ledger_by_id) != len(ledger) or set(ledger_by_id) != set(expected_ids):
        errors.append("exclusion_ledger_record_coverage_invalid")
    for record in records:
        record_id = str(record.get("record_id") or "")
        ledger_row = ledger_by_id.get(record_id) or {}
        if any(ledger_row.get(field) != record.get(field) for field in ("source_lineage_id", "scenario_family_id", "input_fingerprint_sha256")):
            errors.append(f"ledger:{record_id}:identity_mismatch")
        comparators = ledger_row.get("comparators") or {}
        if set(comparators) != REQUIRED_COMPARATORS or any(comparators.get(name) != "no_overlap" for name in REQUIRED_COMPARATORS):
            errors.append(f"ledger:{record_id}:comparison_not_proven")
    if manifest.get("status") != "T42_STUDY_FROZEN_MANIFEST":
        errors.append("manifest_not_frozen")
    if manifest.get("eligibility_validation_status") != "T42_SINGLE_AMBIGUITY_ELIGIBILITY_PASSED":
        errors.append("manifest_eligibility_status_invalid")
    if manifest.get("records_sha256") != _sha256(records_path) or manifest.get("exclusion_ledger_sha256") != _sha256(ledger_path):
        errors.append("manifest_hash_mismatch")
    if manifest.get("record_ids") != expected_ids:
        errors.append("manifest_record_order_invalid")
    for field in ("freeze_id", "source_audit_sha256", "protocol_sha256", "fixed_inference_configuration_sha256"):
        if field == "freeze_id":
            if not isinstance(manifest.get(field), str) or not manifest[field]:
                errors.append("manifest_freeze_id_invalid")
        elif not _is_sha256(manifest.get(field)):
            errors.append(f"manifest_{field}_invalid")
    return errors


def _run_scaffold(args: argparse.Namespace) -> int:
    scaffold = _load_json(args.scaffold)
    errors = validate_scaffold(scaffold)
    payload = {"status": "T42_READINESS_SCAFFOLD_PASSED" if not errors else "VERIFY_FAILED", "scaffold_sha256": _sha256(args.scaffold), "errors": errors, "records_created": False, "inference_run": False}
    _write_json(args.output, payload)
    print(json.dumps({"status": payload["status"], "errors": len(errors)}, sort_keys=True))
    return 0 if not errors else 1


def _run_validate(args: argparse.Namespace) -> int:
    scaffold = _load_json(args.scaffold)
    records = _load_jsonl(args.records)
    ledger = _load_jsonl(args.exclusion_ledger)
    manifest = _load_json(args.manifest)
    errors = validate_freeze(scaffold, records, ledger, manifest, args.records, args.exclusion_ledger)
    payload = {"status": "T42_SINGLE_AMBIGUITY_ELIGIBILITY_PASSED" if not errors else "VERIFY_FAILED", "records_sha256": _sha256(args.records), "exclusion_ledger_sha256": _sha256(args.exclusion_ledger), "n_records": len(records), "errors": errors, "metrics_status": "NOT_COMPUTED" if errors else "ELIGIBLE_FOR_SEPARATE_FIXED_SYSTEM_EVALUATION"}
    _write_json(args.output, payload)
    print(json.dumps({"status": payload["status"], "errors": len(errors)}, sort_keys=True))
    return 0 if not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    scaffold = sub.add_parser("scaffold")
    scaffold.add_argument("--scaffold", type=Path, required=True)
    scaffold.add_argument("--output", type=Path, required=True)
    scaffold.set_defaults(run=_run_scaffold)
    validate = sub.add_parser("validate")
    validate.add_argument("--scaffold", type=Path, required=True)
    validate.add_argument("--records", type=Path, required=True)
    validate.add_argument("--exclusion-ledger", type=Path, required=True)
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--output", type=Path, required=True)
    validate.set_defaults(run=_run_validate)
    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
