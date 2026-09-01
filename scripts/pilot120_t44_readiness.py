#!/usr/bin/env python3
"""CPU-only T44 provenance, disjointness, and blinded-review readiness checks.

This tool never acquires a corpus, creates labels, reads model outputs, or runs
inference.  It binds future T44 evidence to immutable manifests and makes a
missing human or source-evidence step visible as NOT_COMPUTED.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "pilot120_t44_readiness_v1"
PILOT_REFERENCE_STATUS = "PILOT120_REFERENCE_PROVENANCE_RECOVERED"
REQUIRED_REFERENCE_CORPORA = ("pilot_120_v1", "t41_new_source", "t42_single_ambiguity")
REQUIRED_EXCLUSION_AXES = ("exact_record", "paraphrase_or_derivation", "scenario_family")
REQUIRED_T41_FIELDS = (
    "intent",
    "cpc",
    "candidate_set",
    "resolution_value",
    "clarification_target_and_wording",
    "rejection_target_and_wording",
    "silent_resolution",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_not_object:{path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing_to_replace_t44_artifact:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256_value(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value.lower())


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _template_or_invalid(payload: dict[str, Any], name: str, expected_status: str) -> list[str]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        return [f"{name}:schema_version_invalid"]
    if payload.get("status") == "TEMPLATE_NOT_EVIDENCE":
        return [f"{name}:template_not_evidence"]
    if payload.get("status") != expected_status:
        return [f"{name}:status_invalid:{payload.get('status')}"]
    return []


def _record_index(records: Any, *, artifact: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    index: dict[str, dict[str, Any]] = {}
    if not isinstance(records, list) or not records:
        return index, [f"{artifact}:records_missing_or_empty"]
    for row in records:
        if not isinstance(row, dict):
            errors.append(f"{artifact}:record_not_object")
            continue
        candidate_id = row.get("candidate_id")
        if not _nonempty(candidate_id):
            errors.append(f"{artifact}:candidate_id_missing")
            continue
        if candidate_id in index:
            errors.append(f"{artifact}:candidate_id_duplicate:{candidate_id}")
            continue
        if not _sha256_value(row.get("source_record_sha256")):
            errors.append(f"{artifact}:source_record_sha256_invalid:{candidate_id}")
            continue
        index[candidate_id] = row
    return index, errors


def validate_provenance(payload: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    errors = _template_or_invalid(payload, "provenance", "FROZEN")
    source = _mapping(payload.get("source"))
    if not _nonempty(source.get("corpus_id")):
        errors.append("provenance:source_corpus_id_missing")
    if not _nonempty(source.get("source_version")):
        errors.append("provenance:source_version_missing")
    retrieval = _mapping(source.get("retrieval"))
    for field in ("source_uri", "retrieved_at", "source_manifest_sha256"):
        if not _nonempty(retrieval.get(field)):
            errors.append(f"provenance:retrieval_{field}_missing")
    if retrieval.get("source_manifest_sha256") is not None and not _sha256_value(retrieval.get("source_manifest_sha256")):
        errors.append("provenance:source_manifest_sha256_invalid")
    licence = _mapping(source.get("licence"))
    if licence.get("decision") != "APPROVED_FOR_THIS_STUDY":
        errors.append("provenance:licence_not_approved_for_this_study")
    if not _nonempty(licence.get("licence_identifier")):
        errors.append("provenance:licence_identifier_missing")
    if not _nonempty(licence.get("reviewer_id")) or not _nonempty(licence.get("reviewed_at")):
        errors.append("provenance:licence_review_attestation_missing")
    evidence = _list(licence.get("evidence"))
    if not evidence:
        errors.append("provenance:licence_evidence_missing")
    for item in evidence:
        if not isinstance(item, dict) or not _nonempty(item.get("evidence_id")) or not _sha256_value(item.get("sha256")):
            errors.append("provenance:licence_evidence_invalid")
            break
    records, record_errors = _record_index(payload.get("records"), artifact="provenance")
    errors.extend(record_errors)
    return errors, records


def _validate_axis(value: Any, *, candidate_id: str, axis: str, reference_id: str) -> list[str]:
    errors: list[str] = []
    item = _mapping(value)
    prefix = f"exclusion:{candidate_id}:{reference_id}:{axis}"
    if item.get("decision") != "NO_MATCH":
        errors.append(f"{prefix}:decision_not_no_match")
    for field in ("method_id", "evidence_ref", "reviewer_id", "reviewed_at"):
        if not _nonempty(item.get(field)):
            errors.append(f"{prefix}:{field}_missing")
    if axis != "exact_record" and item.get("human_review") is not True:
        errors.append(f"{prefix}:human_review_required")
    return errors


def validate_exclusion(payload: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    errors = _template_or_invalid(payload, "exclusion", "FROZEN")
    reference_rows = _list(payload.get("reference_corpora"))
    reference_index: dict[str, dict[str, Any]] = {}
    for row in reference_rows:
        if not isinstance(row, dict) or not _nonempty(row.get("reference_id")):
            errors.append("exclusion:reference_corpus_invalid")
            continue
        reference_id = row["reference_id"]
        if reference_id in reference_index:
            errors.append(f"exclusion:reference_corpus_duplicate:{reference_id}")
            continue
        reference_index[reference_id] = row
    if set(reference_index) != set(REQUIRED_REFERENCE_CORPORA):
        errors.append("exclusion:reference_corpora_must_be_pilot_t41_t42")
    for reference_id in REQUIRED_REFERENCE_CORPORA:
        row = reference_index.get(reference_id, {})
        if row.get("state") != "FROZEN_REFERENCE" or not _sha256_value(row.get("reference_manifest_sha256")):
            errors.append(f"exclusion:reference_not_frozen:{reference_id}")

    records, record_errors = _record_index(payload.get("records"), artifact="exclusion")
    errors.extend(record_errors)
    for candidate_id, row in records.items():
        if row.get("disposition") != "ELIGIBLE":
            errors.append(f"exclusion:{candidate_id}:disposition_not_eligible")
        comparisons = _mapping(row.get("comparisons"))
        if set(comparisons) != set(REQUIRED_REFERENCE_CORPORA):
            errors.append(f"exclusion:{candidate_id}:reference_comparisons_incomplete")
        for reference_id in REQUIRED_REFERENCE_CORPORA:
            axes = _mapping(comparisons.get(reference_id))
            if set(axes) != set(REQUIRED_EXCLUSION_AXES):
                errors.append(f"exclusion:{candidate_id}:{reference_id}:axes_incomplete")
            for axis in REQUIRED_EXCLUSION_AXES:
                errors.extend(_validate_axis(axes.get(axis), candidate_id=candidate_id, axis=axis, reference_id=reference_id))
    return errors, records


def validate_review_packet(payload: dict[str, Any]) -> tuple[list[str], set[str]]:
    errors = _template_or_invalid(payload, "review_packet", "FROZEN")
    if not _nonempty(payload.get("packet_id")):
        errors.append("review_packet:packet_id_missing")
    blinding = _mapping(payload.get("blinding"))
    if blinding.get("system_identity_blinded") is not True or blinding.get("annotators_blinded_to_each_other") is not True:
        errors.append("review_packet:blinding_incomplete")
    annotators = _mapping(payload.get("annotators"))
    if not _nonempty(annotators.get("annotator_a_id")) or not _nonempty(annotators.get("annotator_b_id")):
        errors.append("review_packet:annotator_ids_missing")
    elif annotators["annotator_a_id"] == annotators["annotator_b_id"]:
        errors.append("review_packet:annotators_not_independent")
    if not _nonempty(payload.get("adjudication_protocol_id")):
        errors.append("review_packet:adjudication_protocol_missing")
    record_ids = payload.get("candidate_ids")
    if not isinstance(record_ids, list) or not record_ids or any(not _nonempty(value) for value in record_ids) or len(set(record_ids)) != len(record_ids):
        errors.append("review_packet:candidate_ids_invalid")
        candidate_ids: set[str] = set()
    else:
        candidate_ids = set(record_ids)
    coverage = _mapping(payload.get("t41_interpretation_field_coverage"))
    if set(coverage) != set(REQUIRED_T41_FIELDS):
        errors.append("review_packet:t41_field_coverage_incomplete")
    for field in REQUIRED_T41_FIELDS:
        entry = _mapping(coverage.get(field))
        if entry.get("status") not in {"IN_SCOPE", "NOT_COMPUTED"}:
            errors.append(f"review_packet:t41_field_status_invalid:{field}")
        if entry.get("status") == "NOT_COMPUTED" and not _nonempty(entry.get("reason")):
            errors.append(f"review_packet:t41_not_computed_reason_missing:{field}")
    denominators = _mapping(payload.get("denominator_and_eligibility"))
    if not _nonempty(denominators.get("pre_registered_rule_id")):
        errors.append("review_packet:denominator_rule_missing")
    evaluator = _mapping(payload.get("evaluator"))
    if not _nonempty(evaluator.get("version")) or not _sha256_value(evaluator.get("sha256")):
        errors.append("review_packet:evaluator_version_or_hash_missing")
    return errors, candidate_ids


def _pilot_paths(root: Path) -> dict[str, Path]:
    config = root / "configs/evaluation/pilot_120_v1.json"
    config_payload = _load_json(config)
    return {
        "config": config,
        "source": root / str(config_payload["source_canonical_jsonl"]),
        "frozen_manifest": root / str(config_payload["frozen_manifest"]),
        "source_provenance": root / "data/annotations/pilot_120_v1/SOURCE_PROVENANCE.json",
    }


def build_pilot_reference(root: Path) -> dict[str, Any]:
    paths = _pilot_paths(root)
    manifest = _load_json(paths["frozen_manifest"])
    if manifest.get("freeze_id") != "pilot_120_v1" or manifest.get("immutable") is not True or manifest.get("evaluation_only") is not True:
        raise ValueError("pilot120_freeze_boundary_invalid")
    if _sha256(paths["source"]) != manifest.get("hashes", {}).get("source_canonical_jsonl"):
        raise ValueError("pilot120_source_hash_mismatch")
    source_records: list[dict[str, Any]] = []
    with paths["source"].open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"pilot120_source_row_not_object:{line_number}")
                source_records.append(value)
    record_ids = [str(row.get("record_id") or "") for row in source_records]
    if record_ids != manifest.get("record_ids") or len(set(record_ids)) != 120:
        raise ValueError("pilot120_source_denominator_or_order_invalid")
    fingerprint_fields = ("command", "dialogue_history", "scene_context", "capability_context")
    fingerprints = []
    for row in source_records:
        inputs = {field: row.get(field) for field in fingerprint_fields}
        normalised = "\n".join(
            " ".join(str(inputs[field] or "").casefold().split())
            if not isinstance(inputs[field], list)
            else " || ".join(" ".join(str(item).casefold().split()) for item in inputs[field])
            for field in fingerprint_fields
        )
        fingerprints.append(
            {
                "record_id": str(row["record_id"]),
                "exact_record_sha256": _canonical_sha256(inputs),
                "normalised_input_sha256": hashlib.sha256(normalised.encode("utf-8")).hexdigest(),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": PILOT_REFERENCE_STATUS,
        "scope": "pilot120_reference_recovery_only_no_new_data_annotation_or_inference",
        "valid_for_official_use": False,
        "must_not_influence_training_selection_or_tuning": True,
        "input_provenance": {
            name: {"path": str(path.relative_to(root).as_posix()), "sha256": _sha256(path)}
            for name, path in sorted(paths.items())
        },
        "pilot_freeze": {
            "freeze_id": manifest["freeze_id"],
            "n_records": len(source_records),
            "source_sha256": manifest["hashes"]["source_canonical_jsonl"],
            "frozen_manifest_sha256": _sha256(paths["frozen_manifest"]),
        },
        "fingerprint_contract": {
            "fields": list(fingerprint_fields),
            "exact_record_fingerprint": "canonical JSON SHA-256 of the four immutable input fields",
            "normalised_input_fingerprint": "casefolded whitespace-normalised comparison aid only; it is not a paraphrase or scenario-family decision",
        },
        "record_fingerprints": fingerprints,
        "limitations": {
            "paraphrase_or_derivation": "NOT_COMPUTED until named human review is recorded in the T44 exclusion ledger",
            "scenario_family": "NOT_COMPUTED until named human review is recorded in the T44 exclusion ledger",
        },
    }


def validate_pilot_reference(payload: dict[str, Any], *, root: Path) -> list[str]:
    errors = _template_or_invalid(payload, "pilot_reference", PILOT_REFERENCE_STATUS)
    try:
        expected = build_pilot_reference(root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return errors + [f"pilot_reference:current_pilot_recovery_failed:{exc}"]
    for field in ("input_provenance", "pilot_freeze", "fingerprint_contract", "record_fingerprints", "limitations"):
        if payload.get(field) != expected.get(field):
            errors.append(f"pilot_reference:{field}_does_not_match_current_immutable_pilot")
    return errors


def validate_readiness(
    provenance: dict[str, Any],
    exclusion: dict[str, Any],
    review_packet: dict[str, Any],
    pilot_reference: dict[str, Any],
    *,
    root: Path,
) -> dict[str, Any]:
    provenance_errors, provenance_records = validate_provenance(provenance)
    exclusion_errors, exclusion_records = validate_exclusion(exclusion)
    review_errors, review_ids = validate_review_packet(review_packet)
    pilot_errors = validate_pilot_reference(pilot_reference, root=root)
    alignment_errors: list[str] = []
    if set(provenance_records) != set(exclusion_records):
        alignment_errors.append("cross_artifact:candidate_id_sets_differ_between_provenance_and_exclusion")
    elif any(provenance_records[key]["source_record_sha256"] != exclusion_records[key]["source_record_sha256"] for key in provenance_records):
        alignment_errors.append("cross_artifact:candidate_record_hashes_differ_between_provenance_and_exclusion")
    if set(exclusion_records) != review_ids:
        alignment_errors.append("cross_artifact:candidate_id_sets_differ_between_exclusion_and_review_packet")
    problems = provenance_errors + exclusion_errors + review_errors + pilot_errors + alignment_errors
    return {
        "status": "T44_READINESS_VERIFY_PASSED" if not problems else "NOT_COMPUTED",
        "scope": "protocol_and_input_audit_only_no_data_acquisition_annotation_or_inference",
        "valid_for_official_use": False,
        "must_not_influence_training_selection_or_tuning": True,
        "confirmation_status": "NOT_COMPUTED",
        "confirmation_reason": "T44 readiness cannot establish held-out generalisation; it still requires a frozen corpus, double annotation/adjudication, fixed-system evaluation, and terminal metric artifacts.",
        "checks": {
            "licence_and_source_provenance": "PASS" if not provenance_errors else "NOT_COMPUTED",
            "three_axis_family_disjointness": "PASS" if not exclusion_errors and not pilot_errors else "NOT_COMPUTED",
            "blinded_review_packet": "PASS" if not review_errors else "NOT_COMPUTED",
            "cross_artifact_candidate_alignment": "PASS" if not alignment_errors else "NOT_COMPUTED",
        },
        "candidate_denominator": len(provenance_records),
        "problems": problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)
    recovery = subparsers.add_parser("recover-pilot-reference", help="Write a hash-only Pilot-120 comparison reference.")
    recovery.add_argument("--output", type=Path, required=True)
    validate = subparsers.add_parser("validate", help="Validate frozen T44 readiness artifacts without running inference.")
    validate.add_argument("--provenance", type=Path, required=True)
    validate.add_argument("--exclusion", type=Path, required=True)
    validate.add_argument("--review-packet", type=Path, required=True)
    validate.add_argument("--pilot-reference", type=Path, required=True)
    validate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "recover-pilot-reference":
        payload = build_pilot_reference(root)
        _write_json(args.output.resolve(), payload)
    else:
        payload = validate_readiness(
            _load_json(args.provenance.resolve()),
            _load_json(args.exclusion.resolve()),
            _load_json(args.review_packet.resolve()),
            _load_json(args.pilot_reference.resolve()),
            root=root,
        )
        _write_json(args.output.resolve(), payload)
    print(json.dumps({"status": payload["status"], "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
