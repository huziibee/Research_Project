"""Load and validate the frozen model-selection development bake-off set."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ambiguity_manager.annotation.canonical import sha256_hex, sha256_json
from ambiguity_manager.paths import ProjectPaths

SET_ID = "model_selection_development_set_v1"
SET_VERSION = "1.0.0"
DATASET_DIR = "data/development/model_selection_v1"
EXPERIMENT_CONFIG = "configs/experiments/model_selection_development_set_v1.json"

CALIBRATION_ID_RE = re.compile(r"^manual:2026:cal:\d{4}$")
FUTURE_MANUAL_ID_RES = (
    re.compile(r"^manual:2026:main:\d{4}$"),
    re.compile(r"^manual:2026:rsv:\d{4}$"),
    re.compile(r"^manual:2026:hb:\d{4}$"),
)

GOLD_FIELD_NAMES = (
    "gold_intent",
    "gold_route",
    "gold_risk_level",
    "gold_capability_status",
    "gold_ambiguity_present",
    "gold_ambiguity_types",
    "gold_compound_ambiguity",
    "gold_cpc",
    "gold_clarification_targets",
    "gold_selected_frame_id",
    "gold_candidate_ids",
    "gold_interpretation_correct_for_pred",
    "gold_safe_rejection",
    "gold_unsupported_selected",
    "cpc",
    "speech_act",
)

REQUIRED_RECORD_FIELDS = (
    "source",
    "source_record_id",
    "synthetic_or_source_derived",
    "available_gold_weak_fields",
    "metric_eligibility",
    "grouping_key",
    "contamination_status",
    "manual_review_status",
    "excluded_from_future_manual_challenge_set",
)


def normalize_command(command: str) -> str:
    return " ".join(command.strip().lower().split())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def manifest_hash(manifest: dict[str, Any]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    return sha256_json(payload)


def available_gold_fields(gold_row: dict[str, Any] | None) -> list[str]:
    if not gold_row:
        return []
    fields: list[str] = []
    for name in GOLD_FIELD_NAMES:
        if name not in gold_row:
            continue
        value = gold_row[name]
        if value is None:
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        fields.append(name)
    return sorted(fields)


def metric_eligibility_from_row(row: dict[str, Any] | None) -> dict[str, bool]:
    default = {
        "routing": False,
        "ambiguity": False,
        "clarification_decision": False,
        "clarification_target": False,
        "compound_sequence": False,
        "context_benefit": False,
        "intent_slots": False,
        "rejection": False,
        "risk": False,
        "capability": False,
    }
    if not row:
        return default
    raw = row.get("label_eligibility") or row.get("metric_eligibility") or {}
    if not isinstance(raw, dict):
        return default
    return {key: bool(raw.get(key, False)) for key in default}


def is_calibration_record_id(record_id: str) -> bool:
    return bool(CALIBRATION_ID_RE.match(record_id))


def is_future_manual_record_id(record_id: str) -> bool:
    return any(pattern.match(record_id) for pattern in FUTURE_MANUAL_ID_RES)


def dataset_paths(root: Path | None = None) -> dict[str, Path]:
    base = (root or ProjectPaths.from_repo_root().root) / DATASET_DIR
    return {
        "dataset_dir": base,
        "inputs": base / "inputs.jsonl",
        "gold": base / "gold.jsonl",
        "manifest": base / "manifest.json",
        "coverage_report": base / "coverage_report.json",
        "eligibility_report": base / "eligibility_report.json",
        "exclusion_report": base / "exclusion_report.json",
        "quality_controls": base / "quality_controls.json",
        "transport_smoke_ids": base / "transport_smoke_ids.json",
    }


@dataclass(frozen=True)
class ModelSelectionDevelopmentSet:
    manifest: dict[str, Any]
    inputs: list[dict[str, Any]]
    gold: list[dict[str, Any]]
    transport_smoke_ids: list[str]

    @property
    def record_ids(self) -> list[str]:
        return [str(row["record_id"]) for row in self.inputs]

    @property
    def gold_by_id(self) -> dict[str, dict[str, Any]]:
        return {str(row["record_id"]): row for row in self.gold}


def load_model_selection_development_set(root: Path | None = None) -> ModelSelectionDevelopmentSet:
    paths = dataset_paths(root)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    inputs = read_jsonl(paths["inputs"])
    gold = read_jsonl(paths["gold"]) if paths["gold"].is_file() else []
    smoke = json.loads(paths["transport_smoke_ids"].read_text(encoding="utf-8"))
    smoke_ids = list(smoke["record_ids"])
    errors = validate_model_selection_manifest(manifest, inputs=inputs, gold=gold, transport_smoke_ids=smoke_ids)
    if errors:
        raise ValueError("invalid model selection development set:\n- " + "\n- ".join(errors))
    return ModelSelectionDevelopmentSet(
        manifest=manifest,
        inputs=inputs,
        gold=gold,
        transport_smoke_ids=smoke_ids,
    )


def validate_model_selection_manifest(
    manifest: dict[str, Any],
    *,
    inputs: list[dict[str, Any]] | None = None,
    gold: list[dict[str, Any]] | None = None,
    transport_smoke_ids: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []

    if manifest.get("development_only") is not True:
        errors.append("development_only must be true")
    if manifest.get("protected") is not False:
        errors.append("protected must be false")
    if manifest.get("valid_for_official_final_claims") is not False:
        errors.append("valid_for_official_final_claims must be false")

    records = manifest.get("records")
    if not isinstance(records, list) or not records:
        errors.append("records must be a non-empty list")
        return errors

    record_count = manifest.get("record_count")
    if record_count != len(records):
        errors.append("record_count must match records length")

    if not (32 <= len(records) <= 48):
        errors.append("record count must be between 32 and 48 inclusive")

    manifest_ids = [str(entry["record_id"]) for entry in records if isinstance(entry, dict)]
    if len(set(manifest_ids)) != len(manifest_ids):
        errors.append("duplicate record_id in manifest.records")

    for entry in records:
        if not isinstance(entry, dict):
            errors.append("each manifest record must be an object")
            continue
        rid = str(entry.get("record_id", ""))
        for field in REQUIRED_RECORD_FIELDS:
            if field not in entry:
                errors.append(f"{rid or '<unknown>'}: missing {field}")
        if entry.get("excluded_from_future_manual_challenge_set") is not True:
            errors.append(f"{rid}: excluded_from_future_manual_challenge_set must be true")
        if is_calibration_record_id(rid):
            errors.append(f"{rid}: calibration record id is forbidden")
        if is_future_manual_record_id(rid):
            errors.append(f"{rid}: future manual namespace id is forbidden")

    recomputed = manifest_hash(manifest)
    if manifest.get("manifest_hash") != recomputed:
        errors.append("manifest_hash mismatch")

    if inputs is not None:
        input_ids = [str(row["record_id"]) for row in inputs]
        if input_ids != manifest_ids:
            errors.append("inputs.jsonl record order/ids must match manifest.records")
        if len(set(input_ids)) != len(input_ids):
            errors.append("duplicate record_id in inputs.jsonl")

    if gold is not None:
        gold_ids = [str(row["record_id"]) for row in gold]
        if len(set(gold_ids)) != len(gold_ids):
            errors.append("duplicate record_id in gold.jsonl")
        unknown_gold_ids = sorted(set(gold_ids) - set(manifest_ids))
        if unknown_gold_ids:
            errors.append(f"gold.jsonl contains ids absent from manifest: {unknown_gold_ids}")

    if transport_smoke_ids is not None:
        if len(transport_smoke_ids) != 4:
            errors.append("transport smoke subset must contain exactly 4 ids")
        unknown = sorted(set(transport_smoke_ids) - set(manifest_ids))
        if unknown:
            errors.append(f"transport smoke ids not in manifest: {unknown}")

    return errors


def duplicate_analysis(inputs: list[dict[str, Any]]) -> dict[str, Any]:
    exact_commands: dict[str, list[str]] = {}
    normalized_commands: dict[str, list[str]] = {}
    for row in inputs:
        rid = str(row["record_id"])
        command = str(row["command"])
        exact_commands.setdefault(command, []).append(rid)
        normalized_commands.setdefault(normalize_command(command), []).append(rid)

    def groups(mapping: dict[str, list[str]]) -> list[dict[str, Any]]:
        return [
            {"key": key, "record_ids": sorted(ids)}
            for key, ids in sorted(mapping.items())
            if len(ids) > 1
        ]

    return {
        "exact_command_duplicate_groups": groups(exact_commands),
        "normalized_command_duplicate_groups": groups(normalized_commands),
    }


def namespace_exclusion_report(record_ids: list[str]) -> dict[str, Any]:
    calibration_overlap = sorted(rid for rid in record_ids if is_calibration_record_id(rid))
    future_manual_overlap = sorted(rid for rid in record_ids if is_future_manual_record_id(rid))
    return {
        "calibration_id_overlap": calibration_overlap,
        "future_manual_id_overlap": future_manual_overlap,
        "calibration_excluded": len(calibration_overlap) == 0,
        "future_manual_namespace_separated": len(future_manual_overlap) == 0,
    }


def unsupported_label_audit(
    manifest_records: list[dict[str, Any]],
    gold_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    invented: list[dict[str, Any]] = []
    for entry in manifest_records:
        rid = str(entry["record_id"])
        declared = set(entry.get("available_gold_weak_fields") or [])
        observed = set(available_gold_fields(gold_by_id.get(rid)))
        if declared != observed:
            invented.append(
                {
                    "record_id": rid,
                    "declared_fields": sorted(declared),
                    "observed_fields": sorted(observed),
                }
            )
    return {
        "records_with_field_declaration_mismatch": invented,
        "unsupported_label_audit_passed": not invented,
    }
