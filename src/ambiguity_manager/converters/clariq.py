"""ClariQ -> canonical schema auxiliary converter (T08).

Reads only ``data/raw/ClariQ/data/train.tsv``. Never opens question_bank,
qrel files, dev/test splits, or multi-turn data. Maps positive clarifying-
question rows onto clarification-target gold with auxiliary non-robotic scope.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
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

SOURCE_DATASET = "clariq"
MAPPING_VERSION = "clariq-1.0.0"
SOURCE_LICENSE = "unresolved"
ORDERING = "topic_id_numeric_asc_facet_id_asc_question_id_asc_full_row_sha256_asc"
AUTHORITATIVE_FILENAME = "train.tsv"
ORIGINAL_SPLIT = "train"
EXCLUDE_REASON = "source_no_question_marker"
NO_QUESTION_ID = "Q00001"
MAPPING_NOTES = "auxiliary_non_robotic_clarification"

EXPECTED_HEADER: tuple[str, ...] = (
    "topic_id",
    "initial_request",
    "topic_desc",
    "clarification_need",
    "facet_id",
    "facet_desc",
    "question_id",
    "question",
    "answer",
)

ALLOWED_CLARIFICATION_NEED = frozenset({"1", "2", "3", "4"})
TOPIC_ID_RE = re.compile(r"^[0-9]+$")
FACET_ID_RE = re.compile(r"^F[0-9]+$")
QUESTION_ID_RE = re.compile(r"^Q[0-9]+$")


class ClariqHeaderError(RuntimeError):
    """Raised when the source TSV header does not match the expected schema."""


class ClariqConversionError(RuntimeError):
    """Raised on non-recoverable conversion faults (e.g. duplicate output IDs)."""


class ClariqConsistencyError(RuntimeError):
    """Raised when topic-level clarification_need values conflict."""


@dataclass
class ConversionResult:
    records: list[CanonicalRecord] = field(default_factory=list)
    quarantine: list[dict[str, Any]] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedRow:
    fields: dict[str, str]
    source_row_index: int
    malformed_width: bool = False


def full_row_sha256(fields: dict[str, str]) -> str:
    """Return a stable SHA-256 digest over the nine raw source TSV fields."""
    payload = {name: fields[name] for name in EXPECTED_HEADER}
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def source_id_for_row(fields: dict[str, str], row_digest: str | None = None) -> str:
    digest = row_digest if row_digest is not None else full_row_sha256(fields)
    return (
        f"{ORIGINAL_SPLIT}:{fields['topic_id']}:"
        f"{fields['facet_id']}:{fields['question_id']}:{digest}"
    )


def composite_key(fields: dict[str, str]) -> tuple[str, str, str]:
    return (fields["topic_id"], fields["facet_id"], fields["question_id"])


def _sort_key(parsed: ParsedRow) -> tuple[int, str, str, str]:
    topic = parsed.fields["topic_id"]
    topic_num = int(topic) if topic.isdigit() else 0
    return (
        topic_num,
        parsed.fields["facet_id"],
        parsed.fields["question_id"],
        full_row_sha256(parsed.fields),
    )


def _validate_row(fields: dict[str, str]) -> str | None:
    topic_id = fields["topic_id"]
    if not topic_id or not TOPIC_ID_RE.fullmatch(topic_id):
        return "invalid_topic_id"

    facet_id = fields["facet_id"]
    if not facet_id or not FACET_ID_RE.fullmatch(facet_id):
        return "invalid_facet_id"

    question_id = fields["question_id"]
    if not question_id or not QUESTION_ID_RE.fullmatch(question_id):
        return "invalid_question_id"

    clarification_need = fields["clarification_need"]
    if clarification_need not in ALLOWED_CLARIFICATION_NEED:
        return "unknown_clarification_need"

    if not fields["initial_request"].strip():
        return "missing_initial_request"

    if question_id != NO_QUESTION_ID and not fields["question"].strip():
        return "missing_question"

    return None


def _read_rows(source: Path) -> list[ParsedRow]:
    rows: list[ParsedRow] = []
    with source.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ClariqHeaderError("empty TSV file") from exc

        if tuple(header) != EXPECTED_HEADER:
            raise ClariqHeaderError(
                f"header mismatch: expected {EXPECTED_HEADER!r}, got {tuple(header)!r}"
            )

        for line_number, parts in enumerate(reader, start=2):
            malformed_width = len(parts) != len(EXPECTED_HEADER)
            fields = {
                name: (parts[i] if i < len(parts) else "") for i, name in enumerate(EXPECTED_HEADER)
            }
            rows.append(
                ParsedRow(
                    fields=fields,
                    source_row_index=line_number,
                    malformed_width=malformed_width,
                )
            )

    return rows


def _quarantine_entry(
    fields: dict[str, str],
    source_row_index: int,
    reason: str,
    details: str,
    source_id: str | None = None,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "reason": reason,
        "details": details,
        "source_row_index": source_row_index,
        "source_row": dict(fields),
    }


def _excluded_entry(
    fields: dict[str, str],
    source_row_index: int,
    source_id: str,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "reason": EXCLUDE_REASON,
        "source_row_index": source_row_index,
        "source_row": dict(fields),
    }


def _label_eligibility() -> LabelEligibility:
    return LabelEligibility(
        routing=False,
        ambiguity=False,
        risk=False,
        capability=False,
        clarification_decision=False,
        clarification_target=True,
        intent_slots=False,
        rejection=False,
        compound_sequence=False,
        context_benefit=False,
    )


def _build_record(fields: dict[str, str], source_row_index: int, source_id: str) -> CanonicalRecord:
    command = fields["initial_request"].strip()
    question = fields["question"].strip()
    source_metadata = {
        **{name: fields[name] for name in EXPECTED_HEADER},
        "source_row_index": source_row_index,
    }
    return CanonicalRecord(
        id=f"{SOURCE_DATASET}:{source_id}",
        record_class=RecordClass.SOURCE_CONVERTED,
        source_dataset=SOURCE_DATASET,
        source_id=source_id,
        original_split=ORIGINAL_SPLIT,
        group_id=f"{SOURCE_DATASET}:topic:{fields['topic_id']}",
        split_status=SplitStatus.UNSPLIT,
        command=command,
        scene_context=None,
        dialogue_history=[],
        capability_context=None,
        candidate_interpretations=[],
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
        gold_clarification_question=question,
        clarification_subtype=None,
        resolved_interpretation=None,
        intent=None,
        slots={},
        annotation_status=AnnotationStatus.WEAK_MAPPED,
        label_confidence=LabelConfidence.WEAK_DERIVED,
        label_eligibility=_label_eligibility(),
        mapping_version=MAPPING_VERSION,
        source_license=SOURCE_LICENSE,
        mapping_notes=MAPPING_NOTES,
        source_metadata=source_metadata,
        schema_version=CANONICAL_SCHEMA_VERSION,
    )


def _duplicate_classification(validated: list[ParsedRow]) -> dict[str, int]:
    exact_groups: dict[str, list[ParsedRow]] = defaultdict(list)
    composite_groups: dict[tuple[str, str, str], list[ParsedRow]] = defaultdict(list)

    for parsed in validated:
        digest = full_row_sha256(parsed.fields)
        exact_groups[digest].append(parsed)
        composite_groups[composite_key(parsed.fields)].append(parsed)

    composite_collision_groups = sum(1 for group in composite_groups.values() if len(group) > 1)
    rows_in_composite_collision_groups = sum(
        len(group) for group in composite_groups.values() if len(group) > 1
    )

    exact_duplicate_groups = sum(1 for group in exact_groups.values() if len(group) > 1)
    exact_duplicate_rows_beyond_first = sum(
        len(group) - 1 for group in exact_groups.values() if len(group) > 1
    )

    conflicting_composite_groups = 0
    distinct_rows_in_conflicting_composite_groups = 0
    for group in composite_groups.values():
        if len(group) <= 1:
            continue
        digests = {full_row_sha256(item.fields) for item in group}
        if len(digests) > 1:
            conflicting_composite_groups += 1
            distinct_rows_in_conflicting_composite_groups += len(digests)

    return {
        "composite_collision_groups": composite_collision_groups,
        "rows_in_composite_collision_groups": rows_in_composite_collision_groups,
        "exact_duplicate_groups": exact_duplicate_groups,
        "exact_duplicate_rows_beyond_first": exact_duplicate_rows_beyond_first,
        "conflicting_composite_groups": conflicting_composite_groups,
        "distinct_rows_in_conflicting_composite_groups": distinct_rows_in_conflicting_composite_groups,
    }


def _check_topic_clarification_need_consistency(rows: list[ParsedRow]) -> None:
    topic_values: dict[str, str] = {}
    for parsed in rows:
        reason = _validate_row(parsed.fields)
        if reason is not None:
            continue
        topic_id = parsed.fields["topic_id"]
        value = parsed.fields["clarification_need"]
        prior = topic_values.get(topic_id)
        if prior is not None and prior != value:
            raise ClariqConsistencyError(
                f"topic_id {topic_id!r} has conflicting clarification_need values "
                f"{prior!r} and {value!r}"
            )
        topic_values[topic_id] = value


def convert_file(source_path: str | Path) -> ConversionResult:
    """Convert one ClariQ ``train.tsv`` file."""
    source = Path(source_path)
    parsed_rows = _read_rows(source)
    source_rows_read = len(parsed_rows)

    validated: list[ParsedRow] = []
    quarantine: list[dict[str, Any]] = []
    quarantine_reasons: dict[str, int] = {}

    for parsed in parsed_rows:
        if parsed.malformed_width:
            reason = "malformed_row"
            quarantine.append(
                _quarantine_entry(
                    parsed.fields,
                    parsed.source_row_index,
                    reason,
                    f"expected {len(EXPECTED_HEADER)} columns",
                )
            )
            quarantine_reasons[reason] = quarantine_reasons.get(reason, 0) + 1
            continue

        reason = _validate_row(parsed.fields)
        if reason is not None:
            quarantine.append(
                _quarantine_entry(
                    parsed.fields,
                    parsed.source_row_index,
                    reason,
                    reason,
                )
            )
            quarantine_reasons[reason] = quarantine_reasons.get(reason, 0) + 1
            continue

        validated.append(parsed)

    _check_topic_clarification_need_consistency(validated)

    duplicate_stats = _duplicate_classification(validated)

    records: list[CanonicalRecord] = []
    excluded: list[dict[str, Any]] = []
    exclusion_reasons: dict[str, int] = {}
    skipped = 0
    skip_reasons: dict[str, int] = {}

    seen_exact_hash: set[str] = set()
    raw_q00001_rows = 0

    for parsed in sorted(validated, key=_sort_key):
        fields = parsed.fields
        row_digest = full_row_sha256(fields)
        source_id = source_id_for_row(fields, row_digest)

        if row_digest in seen_exact_hash:
            quarantine.append(
                _quarantine_entry(
                    fields,
                    parsed.source_row_index,
                    "duplicate_exact_row",
                    f"duplicate of prior row with digest {row_digest}",
                    source_id=source_id,
                )
            )
            quarantine_reasons["duplicate_exact_row"] = (
                quarantine_reasons.get("duplicate_exact_row", 0) + 1
            )
            if fields["question_id"] == NO_QUESTION_ID:
                raw_q00001_rows += 1
            continue

        seen_exact_hash.add(row_digest)

        if fields["question_id"] == NO_QUESTION_ID:
            raw_q00001_rows += 1
            excluded.append(_excluded_entry(fields, parsed.source_row_index, source_id))
            exclusion_reasons[EXCLUDE_REASON] = exclusion_reasons.get(EXCLUDE_REASON, 0) + 1
            continue

        record = _build_record(fields, parsed.source_row_index, source_id)
        try:
            validate_canonical_record(record)
        except Exception as exc:  # noqa: BLE001
            quarantine.append(
                _quarantine_entry(
                    fields,
                    parsed.source_row_index,
                    "schema_validation_failed",
                    str(exc),
                    source_id=source_id,
                )
            )
            quarantine_reasons["schema_validation_failed"] = (
                quarantine_reasons.get("schema_validation_failed", 0) + 1
            )
            continue

        records.append(record)

    seen_output_ids: set[str] = set()
    for record in records:
        if record.id in seen_output_ids:
            raise ClariqConversionError(f"duplicate output id {record.id!r}")
        seen_output_ids.add(record.id)

    rows_converted = len(records)
    rows_quarantined = len(quarantine)
    rows_excluded = len(excluded)

    if source_rows_read != rows_converted + rows_quarantined + rows_excluded + skipped:
        raise ClariqConversionError(
            "accounting invariant failed: "
            f"{source_rows_read} != {rows_converted} + {rows_quarantined} + "
            f"{rows_excluded} + {skipped}"
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
        "rows_skipped": skipped,
        "rows_excluded_by_policy": rows_excluded,
        "raw_q00001_rows": raw_q00001_rows,
        "unique_q00001_rows_excluded": exclusion_reasons.get(EXCLUDE_REASON, 0),
        "skip_reasons": dict(sorted(skip_reasons.items())),
        "quarantine_reasons": dict(sorted(quarantine_reasons.items())),
        "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
        "output_ids_unique": len(seen_output_ids),
        "ordering": ORDERING,
        **duplicate_stats,
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
    """Convert ClariQ train.tsv and write canonical, quarantine, excluded, and summary artefacts."""
    resolve_writable_path(output_path)
    resolve_writable_path(quarantine_path)
    resolve_writable_path(excluded_path)
    resolve_writable_path(summary_path)

    source = Path(source_path)
    result = convert_file(source)
    output = write_canonical_jsonl(output_path, result.records)
    quarantine = _write_jsonl(quarantine_path, result.quarantine)
    excluded = _write_jsonl(excluded_path, result.excluded)
    summary = dict(result.summary)
    summary["output_path"] = repo_relative_path(output)
    summary["quarantine_path"] = repo_relative_path(quarantine)
    summary["excluded_path"] = repo_relative_path(excluded)
    summary["summary_path"] = repo_relative_path(summary_path)
    summary["authoritative_file_only"] = source.resolve() == default_source_path().resolve()
    _write_summary_json(summary_path, summary)
    return summary


def default_source_path(start: Path | None = None) -> Path:
    from ambiguity_manager.paths import ProjectPaths

    path = ProjectPaths.from_repo_root(start).data_raw / "ClariQ" / "data" / AUTHORITATIVE_FILENAME
    if path.name != AUTHORITATIVE_FILENAME:
        raise ClariqConversionError(f"authoritative ClariQ path must be {AUTHORITATIVE_FILENAME!r}")
    return path
