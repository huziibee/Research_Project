"""AmbiK -> canonical schema converter (T03).

Scope and guarantees:

- Reads only the single authoritative primary CSV (``AmbiK/AmbiK_data.csv``).
  Auxiliary AmbiK CSVs are never opened or merged.
- Produces exactly one canonical record per convertible source row.
- Maps the coarse AmbiK ``ambiguity_type`` onto the frozen project taxonomy
  deterministically. Because the canonical labels are *derived* mappings, the
  whole record is marked ``weak_mapped`` / ``weak_derived`` even though the
  underlying AmbiK categories and clarification text are source-native.
- Never fabricates ``risk_level``, ``capability_status``, routing labels,
  strategy sequences, slot structures, or compound ambiguity.
- Preserves all 15 source columns verbatim in ``source_metadata``. List-like
  source fields (``variants``, ``amb_shortlist``, ``user_intent``, plans) are
  kept as raw strings; T03 does not parse them into structured canonical fields
  and never uses ``eval``/``ast``/``json`` on source values.
- All project-owned writes route through :func:`resolve_writable_path`.
"""

from __future__ import annotations

import csv
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

SOURCE_DATASET = "ambik"
MAPPING_VERSION = "ambik-1.0.0"
SOURCE_LICENSE = "unresolved"
ORDERING = "source_id_numeric_asc"

EXPECTED_HEADER: tuple[str, ...] = (
    "id",
    "environment_short",
    "environment_full",
    "unambiguous_direct",
    "ambiguity_type",
    "amb_shortlist",
    "ambiguous_task",
    "question",
    "answer",
    "plan_for_clear_task",
    "plan_for_amb_task",
    "end_of_ambiguity",
    "user_intent",
    "variants",
    "take_amb",
)

# Deterministic, human-approved mapping of AmbiK coarse ambiguity categories
# onto the frozen project taxonomy (see docs/mapping/ambik_mapping.md).
AMBIGUITY_TYPE_MAP: dict[str, AmbiguityType] = {
    "preferences": AmbiguityType.PREFERENCE,
    "common_sense_knowledge": AmbiguityType.COMMONSENSE,
    "safety": AmbiguityType.SAFETY_PRECONDITION,
}


class AmbikHeaderError(RuntimeError):
    """Raised when the source CSV header does not match the expected schema."""


class AmbikConversionError(RuntimeError):
    """Raised on non-recoverable conversion faults (e.g. duplicate output IDs)."""


@dataclass
class ConversionResult:
    records: list[CanonicalRecord] = field(default_factory=list)
    quarantine: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def _clean(value: Any) -> str:
    return value if isinstance(value, str) else ("" if value is None else str(value))


def _mapping_notes(raw_type: str, canonical: AmbiguityType) -> str:
    return (
        f"AmbiK ambiguity_type '{raw_type}' deterministically mapped to "
        f"'{canonical.value}' (mapping_version {MAPPING_VERSION}). ambiguity and "
        "clarification_target labels are mapped-source labels, not manually "
        "adjudicated gold. No route, risk, capability, or slot labels are "
        "provided by the source."
    )


def _build_record(row: dict[str, str], raw_type: str) -> CanonicalRecord:
    canonical = AMBIGUITY_TYPE_MAP[raw_type]
    source_id = _clean(row["id"]).strip()
    risk_relevant = canonical == AmbiguityType.SAFETY_PRECONDITION

    source_metadata = {key: _clean(row.get(key)) for key in EXPECTED_HEADER}

    return CanonicalRecord(
        id=f"ambik:{source_id}",
        record_class=RecordClass.SOURCE_CONVERTED,
        source_dataset=SOURCE_DATASET,
        command=_clean(row["ambiguous_task"]),
        annotation_status=AnnotationStatus.WEAK_MAPPED,
        label_confidence=LabelConfidence.WEAK_DERIVED,
        label_eligibility=LabelEligibility(ambiguity=True, clarification_target=True),
        schema_version=CANONICAL_SCHEMA_VERSION,
        source_id=source_id,
        original_split=None,
        group_id=f"ambik:group:{source_id}",
        split_status=SplitStatus.UNSPLIT,
        scene_context=_clean(row["environment_full"]),
        dialogue_history=[],
        capability_context=None,
        ambiguity_present=True,
        ambiguity_types=[canonical],
        primary_ambiguity_type=canonical,
        compound_ambiguity=False,
        compound_ambiguity_count=1,
        missing_slots=[],
        risk_relevant=risk_relevant,
        risk_level=None,
        capability_status=None,
        recommended_strategy=None,
        strategy_sequence=[],
        gold_clarification_question=_clean(row["question"]),
        clarification_subtype=None,
        resolved_interpretation=_clean(row["unambiguous_direct"]),
        intent=None,
        slots={},
        mapping_version=MAPPING_VERSION,
        source_license=SOURCE_LICENSE,
        mapping_notes=_mapping_notes(raw_type, canonical),
        source_metadata=source_metadata,
    )


def _quarantine_entry(source_id: str, row: dict[str, str], reason: str, details: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "reason": reason,
        "details": details,
        "source_row": {key: _clean(row.get(key)) for key in EXPECTED_HEADER},
    }


def _read_rows(source_path: Path) -> list[dict[str, str]]:
    with source_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise AmbikHeaderError("source CSV is empty (missing header row)") from exc
        if tuple(header) != EXPECTED_HEADER:
            raise AmbikHeaderError(
                f"unexpected AmbiK header: expected {list(EXPECTED_HEADER)}, got {header}"
            )
        rows: list[dict[str, str]] = []
        for values in reader:
            row = {name: (values[i] if i < len(values) else "") for i, name in enumerate(EXPECTED_HEADER)}
            row["__width__"] = str(len(values))
            rows.append(row)
    return rows


def convert_file(source_path: str | Path) -> ConversionResult:
    """Convert the AmbiK primary CSV into canonical records with row accounting."""
    source = Path(source_path)
    rows = _read_rows(source)

    records: list[CanonicalRecord] = []
    quarantine: list[dict[str, Any]] = []
    skipped = 0
    skip_reasons: dict[str, int] = {}
    quarantine_reasons: dict[str, int] = {}

    for row in rows:
        width = int(row.pop("__width__"))
        source_id = _clean(row.get("id")).strip()

        if all(not _clean(row.get(k)).strip() for k in EXPECTED_HEADER):
            skipped += 1
            skip_reasons["blank_row"] = skip_reasons.get("blank_row", 0) + 1
            continue

        if width != len(EXPECTED_HEADER):
            quarantine.append(_quarantine_entry(source_id, row, "malformed_row", f"field_count={width}"))
            quarantine_reasons["malformed_row"] = quarantine_reasons.get("malformed_row", 0) + 1
            continue

        if not source_id:
            quarantine.append(_quarantine_entry(source_id, row, "missing_source_id", "empty id"))
            quarantine_reasons["missing_source_id"] = quarantine_reasons.get("missing_source_id", 0) + 1
            continue

        if not _clean(row.get("ambiguous_task")).strip():
            quarantine.append(_quarantine_entry(source_id, row, "missing_command", "empty ambiguous_task"))
            quarantine_reasons["missing_command"] = quarantine_reasons.get("missing_command", 0) + 1
            continue

        raw_type = _clean(row.get("ambiguity_type")).strip()
        if raw_type not in AMBIGUITY_TYPE_MAP:
            quarantine.append(
                _quarantine_entry(source_id, row, "unknown_ambiguity_type", f"value={raw_type!r}")
            )
            quarantine_reasons["unknown_ambiguity_type"] = (
                quarantine_reasons.get("unknown_ambiguity_type", 0) + 1
            )
            continue

        if not _clean(row.get("question")).strip():
            quarantine.append(
                _quarantine_entry(source_id, row, "missing_clarification_question", "empty question")
            )
            quarantine_reasons["missing_clarification_question"] = (
                quarantine_reasons.get("missing_clarification_question", 0) + 1
            )
            continue

        if not _clean(row.get("unambiguous_direct")).strip():
            quarantine.append(
                _quarantine_entry(
                    source_id,
                    row,
                    "missing_resolved_interpretation",
                    "empty unambiguous_direct",
                )
            )
            quarantine_reasons["missing_resolved_interpretation"] = (
                quarantine_reasons.get("missing_resolved_interpretation", 0) + 1
            )
            continue

        record = _build_record(row, raw_type)
        try:
            validate_canonical_record(record)
        except Exception as exc:  # schema failure => quarantine, never silent loss
            quarantine.append(
                _quarantine_entry(source_id, row, "schema_validation_failed", str(exc))
            )
            quarantine_reasons["schema_validation_failed"] = (
                quarantine_reasons.get("schema_validation_failed", 0) + 1
            )
            continue

        records.append(record)

    records.sort(key=lambda r: int(r.source_id) if (r.source_id or "").isdigit() else 0)

    seen: set[str] = set()
    for record in records:
        if record.id in seen:
            raise AmbikConversionError(f"duplicate output id {record.id!r}")
        seen.add(record.id)

    converted_by_type: dict[str, int] = {}
    for record in records:
        key = record.primary_ambiguity_type.value if record.primary_ambiguity_type else "none"
        converted_by_type[key] = converted_by_type.get(key, 0) + 1

    summary = {
        "converter": SOURCE_DATASET,
        "mapping_version": MAPPING_VERSION,
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "source_path": repo_relative_path(source),
        "source_sha256": streaming_sha256(source),
        "source_rows_read": len(rows),
        "rows_converted": len(records),
        "rows_skipped": skipped,
        "rows_quarantined": len(quarantine),
        "skip_reasons": dict(sorted(skip_reasons.items())),
        "quarantine_reasons": dict(sorted(quarantine_reasons.items())),
        "output_ids_unique": len(seen),
        "converted_by_ambiguity_type": dict(sorted(converted_by_type.items())),
        "ambiguity_type_mapping": {k: v.value for k, v in AMBIGUITY_TYPE_MAP.items()},
        "ordering": ORDERING,
        "auxiliary_csvs_used": False,
    }

    return ConversionResult(records=records, quarantine=quarantine, summary=summary)


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
    target.write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def run_conversion(
    source_path: str | Path,
    output_path: str | Path,
    quarantine_path: str | Path,
    summary_path: str | Path,
) -> dict[str, Any]:
    """Convert AmbiK and write canonical, quarantine, and summary artefacts.

    The canonical output path is validated first so an accidental ``data/raw``
    target is rejected before any file is written.
    """
    resolve_writable_path(output_path)
    resolve_writable_path(quarantine_path)
    resolve_writable_path(summary_path)

    result = convert_file(source_path)

    output = write_canonical_jsonl(output_path, result.records)
    quarantine = _write_quarantine_jsonl(quarantine_path, result.quarantine)
    summary = dict(result.summary)
    summary["output_path"] = repo_relative_path(output)
    summary["quarantine_path"] = repo_relative_path(quarantine)
    summary["summary_path"] = repo_relative_path(summary_path)
    _write_summary_json(summary_path, summary)
    return summary
