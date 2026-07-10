"""CoDraw-iCR v2 -> canonical schema converter (T05).

Reads only the authoritative TSV ``codraw-icr-v2/codraw-icr-v2.tsv``. Never opens
``codraw-icr-v2_raw.tsv``. Maps drawer iCR utterances onto clarification-target
gold with strict instruction anchoring from ``teller_before`` only.
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
    AnnotationStatus,
    LabelConfidence,
    RecordClass,
    SplitStatus,
)
from ambiguity_manager.schema.validation import validate_canonical_record
from ambiguity_manager.schema.version import CANONICAL_SCHEMA_VERSION

SOURCE_DATASET = "codraw_icr_v2"
MAPPING_VERSION = "codraw_icr_v2-1.0.0"
SOURCE_LICENSE = "stated_unverified"
ORDERING = "source_index_numeric_asc"
AUTHORITATIVE_FILENAME = "codraw-icr-v2.tsv"
FORBIDDEN_FILENAME = "codraw-icr-v2_raw.tsv"

EXPECTED_HEADER: tuple[str, ...] = (
    "",
    "teller_before",
    "drawer",
    "teller_after",
    "is_CR_annotator_1",
    "do_annotators_agree",
    "is_CR_annotator_2",
    "mood",
    "is_source_utterance_last_turn",
    "next_turn_contains_response",
    "clipart",
    "clipart_1",
    "clipart_2",
    "clipart_3",
    "clipart_4",
    "clipart_5",
    "position",
    "size",
    "direction",
    "relation_to_other_cliparts",
    "disambig_object",
    "disambig_person",
    "game_name",
    "turn",
    "annotation_round",
    "freq",
)

DOCUMENTED_MOOD_TOKENS = frozenset(
    {
        "declarative",
        "polar question",
        "alternative question",
        "wh- question",
        "imperative",
        "other",
    }
)

MOOD_SPELLING_NORMALIZATION: dict[str, str] = {
    "wh-question": "wh- question",
}

SPLIT_FROM_GAME_NAME: dict[str, tuple[str, SplitStatus]] = {
    "train_": ("train", SplitStatus.TRAIN),
    "val_": ("validation", SplitStatus.DEV),
    "test_": ("test", SplitStatus.TEST),
}


class CodrawIcrV2HeaderError(RuntimeError):
    """Raised when the source TSV header does not match the expected schema."""


@dataclass
class ConversionResult:
    records: list[CanonicalRecord] = field(default_factory=list)
    quarantine: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def _clean(value: Any) -> str:
    return value if isinstance(value, str) else ("" if value is None else str(value))


def normalize_mood(mood: str) -> str | None:
    """Normalize mood tokens for ``clarification_subtype``."""
    if not mood.strip():
        return None
    seen: set[str] = set()
    normalized: list[str] = []
    for part in (segment.strip() for segment in mood.split(",") if segment.strip()):
        token = MOOD_SPELLING_NORMALIZATION.get(part, part)
        if token not in seen:
            seen.add(token)
            normalized.append(token)
    return "; ".join(normalized) if normalized else None


def _unknown_mood_tokens(mood: str) -> list[str]:
    unknown: list[str] = []
    for part in (segment.strip() for segment in mood.split(",") if segment.strip()):
        token = MOOD_SPELLING_NORMALIZATION.get(part, part)
        if token not in DOCUMENTED_MOOD_TOKENS:
            unknown.append(token)
    return unknown


def _mapping_notes() -> str:
    return (
        "CoDraw-iCR v2 record: drawer and mood are source-native clarification "
        "annotations; command is anchored to teller_before when "
        "is_source_utterance_last_turn=1. Complete canonical record is weak-mapped "
        "(annotation_status=weak_mapped, label_confidence=weak_derived). "
        "Content flags and clipart fields are preserved in source_metadata as "
        "clarification-target annotations only; they are not mapped to project "
        "ambiguity taxonomy in T05. teller_after is never used in canonical fields."
    )


def _split_from_game_name(game_name: str) -> tuple[str, SplitStatus] | None:
    for prefix, value in SPLIT_FROM_GAME_NAME.items():
        if game_name.startswith(prefix):
            return value
    return None


def _source_metadata(row: dict[str, str]) -> dict[str, str]:
    return {key: _clean(row.get(key)) for key in EXPECTED_HEADER}


def _quarantine_entry(
    source_id: str,
    row: dict[str, str],
    reason: str,
    details: str,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "reason": reason,
        "details": details,
        "source_row": _source_metadata(row),
    }


def _assert_authoritative_source(path: Path) -> None:
    if path.name == FORBIDDEN_FILENAME:
        raise CodrawIcrV2HeaderError(
            f"refusing to convert auxiliary source file: {path.name}"
        )


def _read_rows(source_path: Path) -> list[dict[str, str]]:
    _assert_authoritative_source(source_path)
    with source_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration as exc:
            raise CodrawIcrV2HeaderError("source TSV is empty (missing header row)") from exc
        if tuple(header) != EXPECTED_HEADER:
            raise CodrawIcrV2HeaderError(
                f"unexpected CoDraw-iCR v2 header: expected {list(EXPECTED_HEADER)}, got {header}"
            )
        rows: list[dict[str, str]] = []
        for values in reader:
            row = {name: (values[i] if i < len(values) else "") for i, name in enumerate(EXPECTED_HEADER)}
            row["__width__"] = str(len(values))
            rows.append(row)
    return rows


def _instruction_available(row: dict[str, str]) -> bool:
    return (
        _clean(row.get("is_source_utterance_last_turn")).strip() == "1"
        and bool(_clean(row.get("teller_before")).strip())
    )


def _build_record(row: dict[str, str], source_id: str) -> CanonicalRecord:
    game_name = _clean(row.get("game_name")).strip()
    split = _split_from_game_name(game_name)
    assert split is not None
    original_split, split_status = split
    mood_raw = _clean(row.get("mood"))

    return CanonicalRecord(
        id=f"codraw_icr_v2:{source_id}",
        record_class=RecordClass.SOURCE_CONVERTED,
        source_dataset=SOURCE_DATASET,
        command=_clean(row.get("teller_before")).strip(),
        annotation_status=AnnotationStatus.WEAK_MAPPED,
        label_confidence=LabelConfidence.WEAK_DERIVED,
        label_eligibility=LabelEligibility(clarification_target=True),
        schema_version=CANONICAL_SCHEMA_VERSION,
        source_id=source_id,
        original_split=original_split,
        group_id=f"codraw_icr_v2:game:{game_name}",
        split_status=split_status,
        scene_context=None,
        dialogue_history=[],
        capability_context=None,
        ambiguity_present=None,
        ambiguity_types=[],
        primary_ambiguity_type=None,
        compound_ambiguity=False,
        compound_ambiguity_count=0,
        missing_slots=[],
        risk_relevant=False,
        risk_level=None,
        capability_status=None,
        recommended_strategy=None,
        strategy_sequence=[],
        gold_clarification_question=_clean(row.get("drawer")).strip(),
        clarification_subtype=normalize_mood(mood_raw),
        resolved_interpretation=None,
        intent=None,
        slots={},
        mapping_version=MAPPING_VERSION,
        source_license=SOURCE_LICENSE,
        mapping_notes=_mapping_notes(),
        source_metadata=_source_metadata(row),
    )


def convert_file(source_path: str | Path) -> ConversionResult:
    """Convert the authoritative CoDraw-iCR v2 TSV into canonical records."""
    source = Path(source_path)
    rows = _read_rows(source)

    records: list[CanonicalRecord] = []
    quarantine: list[dict[str, Any]] = []
    skipped = 0
    skip_reasons: dict[str, int] = {}
    quarantine_reasons: dict[str, int] = {}
    seen_source_ids: set[str] = set()
    unknown_mood_warnings = 0
    clarification_subtype_counts: dict[str, int] = {}
    converted_by_split: dict[str, int] = {"train": 0, "validation": 0, "test": 0}

    for row in rows:
        width = int(row.pop("__width__"))
        source_id = _clean(row.get("")).strip()

        if all(not _clean(row.get(key)).strip() for key in EXPECTED_HEADER):
            skipped += 1
            skip_reasons["blank_row"] = skip_reasons.get("blank_row", 0) + 1
            continue

        if width != len(EXPECTED_HEADER):
            quarantine.append(_quarantine_entry(source_id, row, "malformed_row", f"field_count={width}"))
            quarantine_reasons["malformed_row"] = quarantine_reasons.get("malformed_row", 0) + 1
            continue

        if not source_id:
            quarantine.append(_quarantine_entry(source_id, row, "missing_source_id", "empty source index"))
            quarantine_reasons["missing_source_id"] = quarantine_reasons.get("missing_source_id", 0) + 1
            continue

        if source_id in seen_source_ids:
            quarantine.append(
                _quarantine_entry(source_id, row, "duplicate_source_id", f"duplicate source_id={source_id!r}")
            )
            quarantine_reasons["duplicate_source_id"] = quarantine_reasons.get("duplicate_source_id", 0) + 1
            continue

        if _clean(row.get("is_CR_annotator_2")).strip() != "1":
            quarantine.append(
                _quarantine_entry(source_id, row, "unexpected_non_icr_row", "is_CR_annotator_2 != 1")
            )
            quarantine_reasons["unexpected_non_icr_row"] = (
                quarantine_reasons.get("unexpected_non_icr_row", 0) + 1
            )
            continue

        if not _clean(row.get("drawer")).strip():
            quarantine.append(
                _quarantine_entry(source_id, row, "missing_clarification_utterance", "empty drawer")
            )
            quarantine_reasons["missing_clarification_utterance"] = (
                quarantine_reasons.get("missing_clarification_utterance", 0) + 1
            )
            continue

        game_name = _clean(row.get("game_name")).strip()
        split = _split_from_game_name(game_name)
        if split is None:
            quarantine.append(
                _quarantine_entry(
                    source_id,
                    row,
                    "unknown_game_name_prefix",
                    f"game_name={game_name!r}",
                )
            )
            quarantine_reasons["unknown_game_name_prefix"] = (
                quarantine_reasons.get("unknown_game_name_prefix", 0) + 1
            )
            continue

        if _clean(row.get("is_source_utterance_last_turn")).strip() == "1" and not _clean(
            row.get("teller_before")
        ).strip():
            quarantine.append(_quarantine_entry(source_id, row, "missing_command", "empty teller_before"))
            quarantine_reasons["missing_command"] = quarantine_reasons.get("missing_command", 0) + 1
            continue

        if not _instruction_available(row):
            quarantine.append(
                _quarantine_entry(
                    source_id,
                    row,
                    "source_instruction_unavailable",
                    (
                        "requires is_source_utterance_last_turn=1 and non-empty teller_before; "
                        f"got is_source={_clean(row.get('is_source_utterance_last_turn'))!r}"
                    ),
                )
            )
            quarantine_reasons["source_instruction_unavailable"] = (
                quarantine_reasons.get("source_instruction_unavailable", 0) + 1
            )
            continue

        record = _build_record(row, source_id)
        try:
            validate_canonical_record(record)
        except Exception as exc:
            quarantine.append(
                _quarantine_entry(source_id, row, "schema_validation_failed", str(exc))
            )
            quarantine_reasons["schema_validation_failed"] = (
                quarantine_reasons.get("schema_validation_failed", 0) + 1
            )
            continue

        seen_source_ids.add(source_id)
        records.append(record)
        original_split, _ = split
        converted_by_split[original_split] = converted_by_split.get(original_split, 0) + 1

        mood_raw = _clean(row.get("mood"))
        unknown_mood_warnings += len(_unknown_mood_tokens(mood_raw))
        subtype = record.clarification_subtype or "<empty>"
        clarification_subtype_counts[subtype] = clarification_subtype_counts.get(subtype, 0) + 1

    records.sort(key=lambda item: int(item.source_id) if (item.source_id or "").isdigit() else 0)

    output_ids = [record.id for record in records]
    if len(output_ids) != len(set(output_ids)):
        duplicate_id = next(
            record_id for record_id in output_ids if output_ids.count(record_id) > 1
        )
        raise RuntimeError(f"duplicate output id {duplicate_id!r}")

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
        "output_ids_unique": len(set(output_ids)),
        "converted_by_split": dict(sorted(converted_by_split.items())),
        "clarification_subtype_counts": dict(sorted(clarification_subtype_counts.items())),
        "unknown_mood_token_warnings": unknown_mood_warnings,
        "ordering": ORDERING,
        "auxiliary_raw_used": False,
        "instruction_anchor_policy": "teller_before_when_is_source_utterance_last_turn_eq_1",
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
    target.write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def run_conversion(
    source_path: str | Path,
    output_path: str | Path,
    quarantine_path: str | Path,
    summary_path: str | Path,
) -> dict[str, Any]:
    """Convert CoDraw-iCR v2 and write canonical, quarantine, and summary artefacts."""
    resolve_writable_path(output_path)
    resolve_writable_path(quarantine_path)
    resolve_writable_path(summary_path)

    source = Path(source_path)
    if source.name == FORBIDDEN_FILENAME:
        raise CodrawIcrV2HeaderError(
            f"refusing to convert auxiliary source file: {FORBIDDEN_FILENAME}"
        )

    result = convert_file(source)

    output = write_canonical_jsonl(output_path, result.records)
    quarantine = _write_quarantine_jsonl(quarantine_path, result.quarantine)
    summary = dict(result.summary)
    summary["output_path"] = repo_relative_path(output)
    summary["quarantine_path"] = repo_relative_path(quarantine)
    summary["summary_path"] = repo_relative_path(summary_path)
    _write_summary_json(summary_path, summary)
    return summary
