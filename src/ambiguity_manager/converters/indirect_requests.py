"""IndirectRequests -> canonical schema converter (T04).

Reads only the three authoritative HuggingFace Arrow IPC stream shards under
``data/raw/IndirectRequests/{train,validation,test}/``. Never parses serialized
list strings, never fabricates route/risk/capability labels, and never populates
``resolved_interpretation`` or ``capability_context``.
"""

from __future__ import annotations

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
    AmbiguityType,
    AnnotationStatus,
    LabelConfidence,
    RecordClass,
    SplitStatus,
)
from ambiguity_manager.schema.validation import validate_canonical_record
from ambiguity_manager.schema.version import CANONICAL_SCHEMA_VERSION

SOURCE_DATASET = "indirect_requests"
MAPPING_VERSION = "indirect_requests-1.0.0"
SOURCE_LICENSE = "unresolved"
AMBIGUOUS_TARGET = "<ambiguous>"
ORDERING = "split_train_validation_test_then_row_index_asc"

OFFICIAL_SPLITS: tuple[str, ...] = ("train", "validation", "test")
ARROW_SHARD = "data-00000-of-00001.arrow"

EXPECTED_ARROW_FIELDS: tuple[str, ...] = (
    "creation_date",
    "utterance",
    "slot_description",
    "situation",
    "service",
    "possible_slot_values",
    "bool_rephrased_slot_values",
    "target_slot_value",
    "mean_world_understanding",
)

EXPECTED_ARROW_TYPES: dict[str, str] = {
    "creation_date": "string",
    "utterance": "string",
    "slot_description": "string",
    "situation": "string",
    "service": "string",
    "possible_slot_values": "string",
    "bool_rephrased_slot_values": "string",
    "target_slot_value": "string",
    "mean_world_understanding": "float64",
}

SPLIT_STATUS_MAP: dict[str, SplitStatus] = {
    "train": SplitStatus.TRAIN,
    "validation": SplitStatus.DEV,
    "test": SplitStatus.TEST,
}

_PYARROW_AVAILABLE: bool | None = None


class IndirectRequestsSchemaError(RuntimeError):
    """Raised when an Arrow shard schema does not match the expected layout."""


class IndirectRequestsConversionError(RuntimeError):
    """Raised on non-recoverable conversion faults (e.g. duplicate output IDs)."""


@dataclass
class ConversionResult:
    records: list[CanonicalRecord] = field(default_factory=list)
    quarantine: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def _pyarrow_available() -> bool:
    global _PYARROW_AVAILABLE
    if _PYARROW_AVAILABLE is not None:
        return _PYARROW_AVAILABLE
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        _PYARROW_AVAILABLE = False
    else:
        _PYARROW_AVAILABLE = True
    return _PYARROW_AVAILABLE


def _require_pyarrow() -> None:
    if not _pyarrow_available():
        raise ImportError("pyarrow is required to read IndirectRequests Arrow IPC stream files")


def _arrow_type_name(field_type: Any) -> str:
    import pyarrow as pa

    if pa.types.is_string(field_type) or pa.types.is_large_string(field_type):
        return "string"
    if pa.types.is_float64(field_type):
        return "float64"
    return str(field_type)


def validate_arrow_schema(schema: Any) -> None:
    names = list(schema.names)
    if names != list(EXPECTED_ARROW_FIELDS):
        raise IndirectRequestsSchemaError(
            f"unexpected Arrow fields: expected {list(EXPECTED_ARROW_FIELDS)}, got {names}"
        )
    for name in EXPECTED_ARROW_FIELDS:
        actual = _arrow_type_name(schema.field(name).type)
        expected = EXPECTED_ARROW_TYPES[name]
        if actual != expected:
            raise IndirectRequestsSchemaError(
                f"unexpected type for {name!r}: expected {expected}, got {actual}"
            )


def read_arrow_stream(path: Path) -> list[dict[str, Any]]:
    """Read one IndirectRequests Arrow IPC stream shard into row dicts."""
    _require_pyarrow()
    import pyarrow as pa

    with path.open("rb") as handle:
        reader = pa.ipc.open_stream(handle)
        table = reader.read_all()
    validate_arrow_schema(table.schema)
    rows: list[dict[str, Any]] = []
    for row_index in range(table.num_rows):
        row = {name: table.column(name)[row_index].as_py() for name in EXPECTED_ARROW_FIELDS}
        row["__row_index__"] = row_index
        rows.append(row)
    return rows


def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _is_blank_row(row: dict[str, Any]) -> bool:
    return all(not _clean_str(row.get(field)).strip() for field in EXPECTED_ARROW_FIELDS)


def _mapping_notes(*, ambiguous: bool, target_slot_value: str) -> str:
    if ambiguous:
        return (
            f"target_slot_value is {AMBIGUOUS_TARGET!r}; mapped to ambiguity_present=true "
            f"and pragmatic ambiguity (mapping_version {MAPPING_VERSION}). "
            "intent_slots eligibility disabled. resolved_interpretation and "
            "capability_context remain null by policy."
        )
    return (
        f"target_slot_value {target_slot_value!r} treated as concrete open-vocabulary "
        f"slot gold (mapping_version {MAPPING_VERSION}). ambiguity_present=false. "
        "service preserved in source_metadata only."
    )


def _build_record(row: dict[str, Any], split: str) -> CanonicalRecord:
    row_index = int(row["__row_index__"])
    source_id = f"{split}:{row_index}"
    target_slot_value = _clean_str(row["target_slot_value"]).strip()
    slot_description = _clean_str(row["slot_description"])
    ambiguous = target_slot_value == AMBIGUOUS_TARGET

    source_metadata = {field: row.get(field) for field in EXPECTED_ARROW_FIELDS}

    if ambiguous:
        ambiguity_types = [AmbiguityType.PRAGMATIC]
        primary_ambiguity_type = AmbiguityType.PRAGMATIC
        ambiguity_present = True
        compound_ambiguity_count = 1
        missing_slots = [slot_description] if slot_description else []
        slots: dict[str, Any] = {}
        label_eligibility = LabelEligibility(ambiguity=True, intent_slots=False)
    else:
        ambiguity_types = []
        primary_ambiguity_type = None
        ambiguity_present = False
        compound_ambiguity_count = 0
        missing_slots = []
        slots = {slot_description: target_slot_value} if slot_description else {}
        label_eligibility = LabelEligibility(ambiguity=False, intent_slots=True)

    return CanonicalRecord(
        id=f"indirect_requests:{source_id}",
        record_class=RecordClass.SOURCE_CONVERTED,
        source_dataset=SOURCE_DATASET,
        source_id=source_id,
        original_split=split,
        group_id=None,
        split_status=SPLIT_STATUS_MAP[split],
        command=_clean_str(row["utterance"]),
        scene_context=_clean_str(row["situation"]) or None,
        dialogue_history=[],
        capability_context=None,
        candidate_interpretations=[],
        ambiguity_present=ambiguity_present,
        ambiguity_types=ambiguity_types,
        primary_ambiguity_type=primary_ambiguity_type,
        compound_ambiguity=False,
        compound_ambiguity_count=compound_ambiguity_count,
        missing_slots=missing_slots,
        risk_relevant=False,
        risk_level=None,
        capability_status=None,
        recommended_strategy=None,
        strategy_sequence=[],
        gold_clarification_question=None,
        clarification_subtype=None,
        resolved_interpretation=None,
        intent=None,
        slots=slots,
        annotation_status=AnnotationStatus.WEAK_MAPPED,
        label_confidence=LabelConfidence.WEAK_DERIVED,
        label_eligibility=label_eligibility,
        mapping_version=MAPPING_VERSION,
        source_license=SOURCE_LICENSE,
        mapping_notes=_mapping_notes(ambiguous=ambiguous, target_slot_value=target_slot_value),
        source_metadata=source_metadata,
        schema_version=CANONICAL_SCHEMA_VERSION,
    )


def _quarantine_entry(
    split: str,
    row_index: int,
    row: dict[str, Any],
    reason: str,
    details: str,
) -> dict[str, Any]:
    return {
        "split": split,
        "row_index": row_index,
        "source_id": f"{split}:{row_index}",
        "reason": reason,
        "details": details,
        "source_row": {field: row.get(field) for field in EXPECTED_ARROW_FIELDS},
    }


def convert_split(arrow_path: str | Path, split: str) -> ConversionResult:
    """Convert one official split shard."""
    if split not in SPLIT_STATUS_MAP:
        raise ValueError(f"unsupported split {split!r}")

    source = Path(arrow_path)
    rows = read_arrow_stream(source)

    records: list[CanonicalRecord] = []
    quarantine: list[dict[str, Any]] = []
    skipped = 0
    skip_reasons: dict[str, int] = {}
    quarantine_reasons: dict[str, int] = {}
    ambiguous_count = 0
    concrete_count = 0

    for row in rows:
        row_index = int(row["__row_index__"])

        if _is_blank_row(row):
            skipped += 1
            skip_reasons["blank_row"] = skip_reasons.get("blank_row", 0) + 1
            continue

        if not _clean_str(row.get("utterance")).strip():
            quarantine.append(
                _quarantine_entry(split, row_index, row, "missing_command", "empty utterance")
            )
            quarantine_reasons["missing_command"] = quarantine_reasons.get("missing_command", 0) + 1
            continue

        if not _clean_str(row.get("slot_description")).strip():
            quarantine.append(
                _quarantine_entry(
                    split,
                    row_index,
                    row,
                    "missing_slot_description",
                    "empty slot_description",
                )
            )
            quarantine_reasons["missing_slot_description"] = (
                quarantine_reasons.get("missing_slot_description", 0) + 1
            )
            continue

        target_slot_value = _clean_str(row.get("target_slot_value")).strip()
        if not target_slot_value:
            quarantine.append(
                _quarantine_entry(
                    split,
                    row_index,
                    row,
                    "missing_target_slot_value",
                    "empty target_slot_value",
                )
            )
            quarantine_reasons["missing_target_slot_value"] = (
                quarantine_reasons.get("missing_target_slot_value", 0) + 1
            )
            continue

        record = _build_record(row, split)
        try:
            validate_canonical_record(record)
        except Exception as exc:  # noqa: BLE001
            quarantine.append(
                _quarantine_entry(split, row_index, row, "schema_validation_failed", str(exc))
            )
            quarantine_reasons["schema_validation_failed"] = (
                quarantine_reasons.get("schema_validation_failed", 0) + 1
            )
            continue

        records.append(record)
        if target_slot_value == AMBIGUOUS_TARGET:
            ambiguous_count += 1
        else:
            concrete_count += 1

    if len(records) != ambiguous_count + concrete_count:
        raise IndirectRequestsConversionError(
            "rows_ambiguous + rows_concrete_target must equal rows_converted"
        )

    summary = {
        "split": split,
        "source_path": repo_relative_path(source),
        "source_sha256": streaming_sha256(source),
        "source_rows_read": len(rows),
        "rows_converted": len(records),
        "rows_skipped": skipped,
        "rows_quarantined": len(quarantine),
        "rows_ambiguous": ambiguous_count,
        "rows_concrete_target": concrete_count,
        "skip_reasons": dict(sorted(skip_reasons.items())),
        "quarantine_reasons": dict(sorted(quarantine_reasons.items())),
    }
    return ConversionResult(records=records, quarantine=quarantine, summary=summary)


def convert_dataset(dataset_root: str | Path) -> ConversionResult:
    """Convert all official IndirectRequests splits under ``dataset_root``."""
    root = Path(dataset_root)
    all_records: list[CanonicalRecord] = []
    all_quarantine: list[dict[str, Any]] = []
    per_split: dict[str, dict[str, Any]] = {}
    totals = {
        "source_rows_read": 0,
        "rows_converted": 0,
        "rows_skipped": 0,
        "rows_quarantined": 0,
        "rows_ambiguous": 0,
        "rows_concrete_target": 0,
    }
    skip_reasons: dict[str, int] = {}
    quarantine_reasons: dict[str, int] = {}
    rows_per_split: dict[str, int] = {}

    for split in OFFICIAL_SPLITS:
        arrow_path = root / split / ARROW_SHARD
        if not arrow_path.is_file():
            raise FileNotFoundError(f"missing authoritative shard: {arrow_path}")
        result = convert_split(arrow_path, split)
        all_records.extend(result.records)
        all_quarantine.extend(result.quarantine)
        per_split[split] = result.summary
        rows_per_split[split] = result.summary["source_rows_read"]
        for key in (
            "source_rows_read",
            "rows_converted",
            "rows_skipped",
            "rows_quarantined",
            "rows_ambiguous",
            "rows_concrete_target",
        ):
            totals[key] += result.summary[key]
        for reason, count in result.summary["skip_reasons"].items():
            skip_reasons[reason] = skip_reasons.get(reason, 0) + count
        for reason, count in result.summary["quarantine_reasons"].items():
            quarantine_reasons[reason] = quarantine_reasons.get(reason, 0) + count

    if totals["rows_converted"] != totals["rows_ambiguous"] + totals["rows_concrete_target"]:
        raise IndirectRequestsConversionError(
            "rows_ambiguous + rows_concrete_target must equal rows_converted"
        )

    split_order = {split: index for index, split in enumerate(OFFICIAL_SPLITS)}
    all_records.sort(
        key=lambda record: (
            split_order.get(record.original_split or "", 99),
            int((record.source_id or "0:0").split(":", 1)[1]),
        )
    )

    seen: set[str] = set()
    for record in all_records:
        if record.id in seen:
            raise IndirectRequestsConversionError(f"duplicate output id {record.id!r}")
        seen.add(record.id)

    summary = {
        "converter": SOURCE_DATASET,
        "mapping_version": MAPPING_VERSION,
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "dataset_root": repo_relative_path(root),
        "source_rows_read": totals["source_rows_read"],
        "rows_converted": totals["rows_converted"],
        "rows_skipped": totals["rows_skipped"],
        "rows_quarantined": totals["rows_quarantined"],
        "rows_ambiguous": totals["rows_ambiguous"],
        "rows_concrete_target": totals["rows_concrete_target"],
        "rows_per_split": rows_per_split,
        "per_split": per_split,
        "skip_reasons": dict(sorted(skip_reasons.items())),
        "quarantine_reasons": dict(sorted(quarantine_reasons.items())),
        "output_ids_unique": len(seen),
        "ordering": ORDERING,
    }
    return ConversionResult(records=all_records, quarantine=all_quarantine, summary=summary)


def _write_quarantine_jsonl(path: str | Path, entries: list[dict[str, Any]]) -> Path:
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
    dataset_root: str | Path,
    output_path: str | Path,
    quarantine_path: str | Path,
    summary_path: str | Path,
) -> dict[str, Any]:
    """Convert IndirectRequests and write canonical, quarantine, and summary artefacts."""
    resolve_writable_path(output_path)
    resolve_writable_path(quarantine_path)
    resolve_writable_path(summary_path)

    result = convert_dataset(dataset_root)
    output = write_canonical_jsonl(output_path, result.records)
    quarantine = _write_quarantine_jsonl(quarantine_path, result.quarantine)
    summary = dict(result.summary)
    summary["output_path"] = repo_relative_path(output)
    summary["quarantine_path"] = repo_relative_path(quarantine)
    summary["summary_path"] = repo_relative_path(summary_path)
    _write_summary_json(summary_path, summary)
    return summary


def default_raw_root(start: Path | None = None) -> Path:
    from ambiguity_manager.paths import ProjectPaths

    return ProjectPaths.from_repo_root(start).data_raw / "IndirectRequests"
