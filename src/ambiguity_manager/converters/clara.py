"""CLARA / SaGC -> canonical schema converter (T07).

Reads only ``data/raw/CLARA-Dataset/data/agument.json``. Never fabricates
ambiguity-taxonomy subtypes, risk labels, rejection utterances, or permitted-action
lists beyond the source-native robot ``task`` field.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ambiguity_manager.data_audit.readers import streaming_sha256
from ambiguity_manager.io_guard import resolve_writable_path
from ambiguity_manager.paths import repo_relative_path
from ambiguity_manager.schema.jsonl import write_canonical_jsonl
from ambiguity_manager.schema.records import CanonicalRecord, LabelEligibility
from ambiguity_manager.schema.taxonomies import (
    AnnotationStatus,
    CapabilityStatus,
    LabelConfidence,
    RecordClass,
    RouteLabel,
    SplitStatus,
)
from ambiguity_manager.schema.validation import validate_canonical_record
from ambiguity_manager.schema.version import CANONICAL_SCHEMA_VERSION

SOURCE_DATASET = "clara"
MAPPING_VERSION = "clara-1.0.0"
SOURCE_LICENSE = "unresolved"
ORDERING = "source_index_numeric_asc"
EXCLUDE_LABEL = 3
EXCLUDE_REASON = "source_label_3_semantic_conflict"

ALLOWED_TASKS: frozenset[str] = frozenset({"cooking", "cleaning", "massaging"})
ALLOWED_LABELS: frozenset[int] = frozenset({0, 1, 2, 3})
EXPECTED_RECORD_KEYS: frozenset[str] = frozenset({"scene", "goal", "label", "task"})
EXPECTED_SCENE_KEYS: frozenset[str] = frozenset({"floorplan", "objects", "people"})

AUTHORITATIVE_RELATIVE = Path("CLARA-Dataset/data/agument.json")


class ClaraSchemaError(RuntimeError):
    """Raised when the source JSON top-level shape is invalid."""


class ClaraJsonError(RuntimeError):
    """Raised when JSON parsing fails or duplicate object keys are detected."""


class ClaraConversionError(RuntimeError):
    """Raised on non-recoverable conversion faults (e.g. duplicate output IDs)."""


@dataclass
class ConversionResult:
    records: list[CanonicalRecord] = field(default_factory=list)
    quarantine: list[dict[str, Any]] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def serialize_scene(scene: dict[str, Any]) -> str:
    """Deterministic JSON serialization for scene context and group hashing."""
    return json.dumps(scene, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _scene_group_id(scene: dict[str, Any]) -> str:
    digest = hashlib.sha256(serialize_scene(scene).encode("utf-8")).hexdigest()[:16]
    return f"clara:scene:{digest}"


def _load_json_no_duplicate_keys(text: str) -> Any:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: set[str] = set()
        for key, _ in pairs:
            if key in seen:
                raise ClaraJsonError(f"duplicate JSON object key: {key!r}")
            seen.add(key)
        return dict(pairs)

    try:
        return json.loads(text, object_pairs_hook=hook)
    except json.JSONDecodeError as exc:
        raise ClaraJsonError(f"malformed JSON: {exc}") from exc


def load_clara_dataset(path: Path) -> dict[str, Any]:
    """Load the CLARA source file with duplicate-key detection."""
    text = path.read_text(encoding="utf-8")
    payload = _load_json_no_duplicate_keys(text)
    if not isinstance(payload, dict):
        raise ClaraSchemaError(f"expected top-level JSON object, got {type(payload).__name__}")
    return payload


def normalize_source_id(raw_key: str) -> str | None:
    """Return canonical non-negative decimal source ID or None if invalid."""
    trimmed = raw_key.strip()
    if not trimmed or not trimmed.isdigit():
        return None
    if len(trimmed) > 1 and trimmed[0] == "0":
        return None
    value = int(trimmed)
    if value < 0:
        return None
    return str(value)


def _capability_context(task: str) -> str:
    return f"Robot type: {task}"


def _label_eligibility(label: int) -> LabelEligibility:
    routing = label in {0, 1}
    capability = label in {0, 1}
    return LabelEligibility(
        routing=routing,
        ambiguity=True,
        risk=False,
        capability=capability,
        clarification_decision=True,
        clarification_target=False,
        intent_slots=False,
        rejection=False,
        compound_sequence=False,
        context_benefit=True,
    )


def _mapping_notes(label: int, task: str) -> str:
    if label == 0:
        return (
            f"source label 0 (clear) mapped to ambiguity_present=false, "
            f"capability_status=capable, recommended_strategy=execute "
            f"(mapping_version {MAPPING_VERSION})."
        )
    if label == 1:
        return (
            f"source label 1 (ambiguous) mapped to ambiguity_present=true, "
            f"capability_status=capable, recommended_strategy=clarify "
            f"(mapping_version {MAPPING_VERSION}). ambiguity taxonomy abstained."
        )
    if label == 2:
        return (
            f"source label 2 (infeasible) mapped to ambiguity_present=false, "
            f"capability_status=unknown; route and rejection abstained "
            f"(mapping_version {MAPPING_VERSION})."
        )
    return f"unexpected label {label} for record build"


def _validate_scene(scene: Any) -> str | None:
    if not isinstance(scene, dict):
        return "scene must be an object"
    if set(scene.keys()) != EXPECTED_SCENE_KEYS:
        missing = sorted(EXPECTED_SCENE_KEYS - set(scene.keys()))
        extra = sorted(set(scene.keys()) - EXPECTED_SCENE_KEYS)
        return f"scene keys must be exactly {sorted(EXPECTED_SCENE_KEYS)}; missing={missing} extra={extra}"
    for scene_key in sorted(EXPECTED_SCENE_KEYS):
        items = scene[scene_key]
        if not isinstance(items, list):
            return f"scene.{scene_key} must be a list"
        for index, item in enumerate(items):
            if not isinstance(item, str):
                return f"scene.{scene_key}[{index}] must be a string"
    return None


def _build_record(
    source_id: str,
    row: dict[str, Any],
    label: int,
    command: str,
    task: str,
) -> CanonicalRecord:
    raw_goal = row["goal"]
    raw_task = row["task"]
    scene = row["scene"]
    capability_status: CapabilityStatus | None
    recommended_strategy: RouteLabel | None
    ambiguity_present: bool

    if label == 0:
        ambiguity_present = False
        capability_status = CapabilityStatus.CAPABLE
        recommended_strategy = RouteLabel.EXECUTE
    elif label == 1:
        ambiguity_present = True
        capability_status = CapabilityStatus.CAPABLE
        recommended_strategy = RouteLabel.CLARIFY
    elif label == 2:
        ambiguity_present = False
        capability_status = CapabilityStatus.UNKNOWN
        recommended_strategy = None
    else:
        raise ValueError(f"cannot build canonical record for label {label}")

    source_metadata = {
        "source_index": source_id,
        "goal": raw_goal,
        "label": label,
        "task": raw_task,
        "scene": scene,
    }

    return CanonicalRecord(
        id=f"clara:{source_id}",
        record_class=RecordClass.SOURCE_CONVERTED,
        source_dataset=SOURCE_DATASET,
        source_id=source_id,
        original_split=None,
        group_id=_scene_group_id(scene),
        split_status=SplitStatus.UNSPLIT,
        command=command,
        scene_context=serialize_scene(scene),
        dialogue_history=[],
        capability_context=_capability_context(task),
        candidate_interpretations=[],
        ambiguity_present=ambiguity_present,
        ambiguity_types=[],
        primary_ambiguity_type=None,
        compound_ambiguity=False,
        compound_ambiguity_count=0,
        missing_slots=[],
        risk_relevant=False,
        risk_level=None,
        capability_status=capability_status,
        recommended_strategy=recommended_strategy,
        strategy_sequence=[],
        gold_clarification_question=None,
        clarification_subtype=None,
        resolved_interpretation=None,
        intent=None,
        slots={},
        annotation_status=AnnotationStatus.WEAK_MAPPED,
        label_confidence=LabelConfidence.WEAK_DERIVED,
        label_eligibility=_label_eligibility(label),
        mapping_version=MAPPING_VERSION,
        source_license=SOURCE_LICENSE,
        mapping_notes=_mapping_notes(label, task),
        source_metadata=source_metadata,
        schema_version=CANONICAL_SCHEMA_VERSION,
    )


def _quarantine_entry(
    raw_source_key: str,
    normalized_source_id: str | None,
    row: dict[str, Any] | None,
    reason: str,
    details: str,
) -> dict[str, Any]:
    return {
        "raw_source_key": raw_source_key,
        "source_id": normalized_source_id,
        "reason": reason,
        "details": details,
        "source_row": row,
    }


def _excluded_entry(raw_source_key: str, normalized_source_id: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "raw_source_key": raw_source_key,
        "source_id": normalized_source_id,
        "reason": EXCLUDE_REASON,
        "source_row": {
            "source_index": normalized_source_id,
            "goal": row.get("goal"),
            "label": row.get("label"),
            "task": row.get("task"),
            "scene": row.get("scene"),
        },
    }


def convert_file(source_path: str | Path) -> ConversionResult:
    """Convert one CLARA ``agument.json`` file."""
    source = Path(source_path)
    data = load_clara_dataset(source)

    records: list[CanonicalRecord] = []
    quarantine: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    skipped = 0
    skip_reasons: dict[str, int] = {}
    quarantine_reasons: dict[str, int] = {}
    exclusion_reasons: dict[str, int] = {}
    per_label_converted: dict[str, int] = {}
    per_label_excluded: dict[str, int] = {}

    indexed_rows: list[tuple[int, str, str, dict[str, Any]]] = []
    registered_normalized_ids: dict[str, str] = {}

    for raw_key, row in data.items():
        raw_source_key = str(raw_key)
        normalized_source_id = normalize_source_id(raw_source_key)
        if normalized_source_id is None:
            quarantine.append(
                _quarantine_entry(
                    raw_source_key,
                    None,
                    row if isinstance(row, dict) else None,
                    "invalid_source_id",
                    f"key must be a canonical non-negative decimal string, got {raw_source_key!r}",
                )
            )
            quarantine_reasons["invalid_source_id"] = (
                quarantine_reasons.get("invalid_source_id", 0) + 1
            )
            continue

        if normalized_source_id in registered_normalized_ids:
            prior_raw = registered_normalized_ids[normalized_source_id]
            raise ClaraConversionError(
                f"duplicate normalized source_id {normalized_source_id!r} from raw keys "
                f"{prior_raw!r} and {raw_source_key!r}"
            )
        registered_normalized_ids[normalized_source_id] = raw_source_key

        if not isinstance(row, dict):
            quarantine.append(
                _quarantine_entry(
                    raw_source_key,
                    normalized_source_id,
                    None,
                    "malformed_record",
                    "record is not an object",
                )
            )
            quarantine_reasons["malformed_record"] = quarantine_reasons.get("malformed_record", 0) + 1
            continue

        indexed_rows.append((int(normalized_source_id), normalized_source_id, raw_source_key, row))

    indexed_rows.sort(key=lambda item: item[0])

    for index, source_id, raw_source_key, row in indexed_rows:
        extra_keys = set(row.keys()) - EXPECTED_RECORD_KEYS
        missing_keys = EXPECTED_RECORD_KEYS - set(row.keys())
        if missing_keys or extra_keys:
            quarantine.append(
                _quarantine_entry(
                    raw_source_key,
                    source_id,
                    row,
                    "malformed_record",
                    f"missing={sorted(missing_keys)} extra={sorted(extra_keys)}",
                )
            )
            quarantine_reasons["malformed_record"] = quarantine_reasons.get("malformed_record", 0) + 1
            continue

        scene = row.get("scene")
        scene_error = _validate_scene(scene)
        if scene_error is not None:
            quarantine.append(
                _quarantine_entry(
                    raw_source_key,
                    source_id,
                    row,
                    "missing_scene",
                    scene_error,
                )
            )
            quarantine_reasons["missing_scene"] = quarantine_reasons.get("missing_scene", 0) + 1
            continue

        goal_raw = row.get("goal")
        if not isinstance(goal_raw, str):
            quarantine.append(
                _quarantine_entry(
                    raw_source_key,
                    source_id,
                    row,
                    "non_string_goal",
                    f"goal must be a string, got {type(goal_raw).__name__}",
                )
            )
            quarantine_reasons["non_string_goal"] = quarantine_reasons.get("non_string_goal", 0) + 1
            continue

        command = goal_raw.strip()
        if not command:
            quarantine.append(
                _quarantine_entry(
                    raw_source_key,
                    source_id,
                    row,
                    "missing_command",
                    "empty goal",
                )
            )
            quarantine_reasons["missing_command"] = quarantine_reasons.get("missing_command", 0) + 1
            continue

        label_raw = row.get("label")
        if type(label_raw) is not int:
            quarantine.append(
                _quarantine_entry(
                    raw_source_key,
                    source_id,
                    row,
                    "unknown_label",
                    f"label must be int, got {type(label_raw).__name__}",
                )
            )
            quarantine_reasons["unknown_label"] = quarantine_reasons.get("unknown_label", 0) + 1
            continue

        label = label_raw
        if label not in ALLOWED_LABELS:
            quarantine.append(
                _quarantine_entry(
                    raw_source_key,
                    source_id,
                    row,
                    "unknown_label",
                    f"value={label}",
                )
            )
            quarantine_reasons["unknown_label"] = quarantine_reasons.get("unknown_label", 0) + 1
            continue

        task_raw = row.get("task")
        if not isinstance(task_raw, str):
            quarantine.append(
                _quarantine_entry(
                    raw_source_key,
                    source_id,
                    row,
                    "non_string_task",
                    f"task must be a string, got {type(task_raw).__name__}",
                )
            )
            quarantine_reasons["non_string_task"] = quarantine_reasons.get("non_string_task", 0) + 1
            continue

        task = task_raw.strip()
        if task not in ALLOWED_TASKS:
            quarantine.append(
                _quarantine_entry(
                    raw_source_key,
                    source_id,
                    row,
                    "unknown_task",
                    f"value={task_raw!r}",
                )
            )
            quarantine_reasons["unknown_task"] = quarantine_reasons.get("unknown_task", 0) + 1
            continue

        if label == EXCLUDE_LABEL:
            excluded.append(_excluded_entry(raw_source_key, source_id, row))
            exclusion_reasons[EXCLUDE_REASON] = exclusion_reasons.get(EXCLUDE_REASON, 0) + 1
            per_label_excluded[str(label)] = per_label_excluded.get(str(label), 0) + 1
            continue

        record = _build_record(source_id, row, label, command, task)
        try:
            validate_canonical_record(record)
        except Exception as exc:  # noqa: BLE001
            quarantine.append(
                _quarantine_entry(
                    raw_source_key,
                    source_id,
                    row,
                    "schema_validation_failed",
                    str(exc),
                )
            )
            quarantine_reasons["schema_validation_failed"] = (
                quarantine_reasons.get("schema_validation_failed", 0) + 1
            )
            continue

        records.append(record)
        per_label_converted[str(label)] = per_label_converted.get(str(label), 0) + 1

    seen_output_ids: set[str] = set()
    for record in records:
        if record.id in seen_output_ids:
            raise ClaraConversionError(f"duplicate output id {record.id!r}")
        seen_output_ids.add(record.id)

    source_rows_read = len(data)
    rows_converted = len(records)
    rows_quarantined = len(quarantine)
    rows_excluded = len(excluded)
    rows_skipped = skipped

    if source_rows_read != rows_converted + rows_quarantined + rows_skipped + rows_excluded:
        raise ClaraConversionError(
            "accounting invariant failed: "
            f"{source_rows_read} != {rows_converted} + {rows_quarantined} + "
            f"{rows_skipped} + {rows_excluded}"
        )

    summary = {
        "converter": SOURCE_DATASET,
        "mapping_version": MAPPING_VERSION,
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "source_path": repo_relative_path(source),
        "source_sha256": streaming_sha256(source),
        "source_rows_read": source_rows_read,
        "rows_converted": rows_converted,
        "rows_quarantined": rows_quarantined,
        "rows_skipped": rows_skipped,
        "rows_excluded_by_policy": rows_excluded,
        "per_label_converted": dict(sorted(per_label_converted.items())),
        "per_label_excluded": dict(sorted(per_label_excluded.items())),
        "skip_reasons": dict(sorted(skip_reasons.items())),
        "quarantine_reasons": dict(sorted(quarantine_reasons.items())),
        "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
        "output_ids_unique": len(seen_output_ids),
        "ordering": ORDERING,
    }
    return ConversionResult(
        records=records,
        quarantine=quarantine,
        excluded=excluded,
        summary=summary,
    )


def _write_jsonl(path: str | Path, entries: list[dict[str, Any]]) -> Path:
    target = resolve_writable_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False))
            handle.write("\n")
    return target


def _write_summary_json(path: str | Path, summary: dict[str, Any]) -> Path:
    target = resolve_writable_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def run_conversion(
    source_path: str | Path,
    output_path: str | Path,
    quarantine_path: str | Path,
    excluded_path: str | Path,
    summary_path: str | Path,
) -> dict[str, Any]:
    """Convert CLARA and write canonical, quarantine, excluded, and summary artefacts."""
    resolve_writable_path(output_path)
    resolve_writable_path(quarantine_path)
    resolve_writable_path(excluded_path)
    resolve_writable_path(summary_path)

    result = convert_file(source_path)
    output = write_canonical_jsonl(output_path, result.records)
    quarantine = _write_jsonl(quarantine_path, result.quarantine)
    excluded = _write_jsonl(excluded_path, result.excluded)
    summary = dict(result.summary)
    summary["output_path"] = repo_relative_path(output)
    summary["quarantine_path"] = repo_relative_path(quarantine)
    summary["excluded_path"] = repo_relative_path(excluded)
    summary["summary_path"] = repo_relative_path(summary_path)
    _write_summary_json(summary_path, summary)
    return summary


def default_source_path(start: Path | None = None) -> Path:
    from ambiguity_manager.paths import ProjectPaths

    return ProjectPaths.from_repo_root(start).data_raw / AUTHORITATIVE_RELATIVE
