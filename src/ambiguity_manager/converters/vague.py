"""VAGUE (vague_bench) -> canonical schema converter (T06).

Reads only the authoritative Parquet shard under
``data/raw/vague_bench/data/train-00000-of-00001.parquet``. Never reads
``.cache`` stubs, never materializes ``image.bytes``, and never fabricates
route, risk, capability, or project ambiguity-taxonomy labels.
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
from ambiguity_manager.schema.records import (
    CandidateInterpretation,
    CanonicalRecord,
    LabelEligibility,
)
from ambiguity_manager.schema.taxonomies import (
    AnnotationStatus,
    LabelConfidence,
    RecordClass,
    SplitStatus,
)
from ambiguity_manager.schema.validation import validate_canonical_record
from ambiguity_manager.schema.version import CANONICAL_SCHEMA_VERSION

SOURCE_DATASET = "vague"
MAPPING_VERSION = "vague-1.0.0"
SOURCE_LICENSE = "unresolved"
ORDERING = "row_index_asc"
AUTHORITATIVE_RELATIVE = Path("vague_bench/data/train-00000-of-00001.parquet")
ORIGINAL_SPLIT = "train"

PROJECTED_COLUMNS: tuple[str, ...] = (
    "image_name",
    "direct",
    "indirect",
    "solution",
    "mcq",
    "meta",
)

MCQ_OPTION_KEYS: tuple[str, ...] = (
    "1_correct",
    "2_fake_scene",
    "3_surface_understanding",
    "4_wrong_entity",
)

MCQ_SCHEMA_CHILDREN: tuple[tuple[str, str], ...] = (
    ("1_correct", "string"),
    ("2_fake_scene", "string"),
    ("3_surface_understanding", "string"),
    ("4_wrong_entity", "string"),
    ("ordering", "list_string"),
)

META_SCHEMA_CHILDREN: tuple[tuple[str, str], ...] = (
    ("caption", "string"),
    ("ram_entity", "list_string"),
    ("img_size", "img_size_struct"),
    ("person_bbox", "list_list_float32"),
    ("rating", "rating_struct"),
    ("fake_caption", "string"),
)

VALID_MCQ_ORDERING_LETTERS: frozenset[str] = frozenset({"A", "B", "C", "D"})

_PYARROW_AVAILABLE: bool | None = None


class VagueSchemaError(RuntimeError):
    """Raised when the Parquet schema does not match the expected layout."""


class VagueConversionError(RuntimeError):
    """Raised on non-recoverable conversion faults (e.g. duplicate image_name)."""


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
        raise ImportError("pyarrow is required to read VAGUE Parquet files")


def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def parse_solution_triplet(solution: str) -> tuple[dict[str, str] | None, str | None]:
    """Parse a VAGUE solution triplet into canonical slots.

    Returns ``(slots, quarantine_reason)``. Uses comma splitting only; never
    ``eval`` or ``ast.literal_eval``.
    """
    raw = solution.strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1].strip()
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 3:
        return None, "invalid_solution_triplet"
    subject, action, obj = parts
    if not subject or not action or not obj:
        return None, "invalid_solution_triplet"
    return {"subject": subject, "action": action, "object": obj}, None


def _register_image_name(image_name: str, seen: set[str]) -> None:
    if image_name in seen:
        raise VagueConversionError(f"duplicate image_name {image_name!r}")
    seen.add(image_name)


def _subcorpus(image_name: str) -> str:
    return "vcr" if "@" in image_name else "ego4d"


def _is_string_type(field_type: Any) -> bool:
    import pyarrow as pa

    return pa.types.is_string(field_type) or pa.types.is_large_string(field_type)


def _is_list_of(field_type: Any, element_predicate: Any) -> bool:
    import pyarrow as pa

    if not pa.types.is_list(field_type):
        return False
    return element_predicate(field_type.value_type)


def _validate_img_size_struct(field_type: Any, path: str) -> None:
    import pyarrow as pa

    if not pa.types.is_struct(field_type):
        raise VagueSchemaError(f"expected struct for {path}, got {field_type}")
    children = {field.name: field.type for field in field_type}
    for name in ("width", "height"):
        child_path = f"{path}.{name}"
        if name not in children:
            raise VagueSchemaError(f"missing required schema child {child_path}")
        if not pa.types.is_float32(children[name]):
            raise VagueSchemaError(
                f"incorrect type for {child_path}: expected float32, got {children[name]}"
            )


def _validate_rating_struct(field_type: Any, path: str) -> None:
    import pyarrow as pa

    if not pa.types.is_struct(field_type):
        raise VagueSchemaError(f"expected struct for {path}, got {field_type}")
    children = {field.name: field.type for field in field_type}
    for name in ("direct", "indirect"):
        child_path = f"{path}.{name}"
        if name not in children:
            raise VagueSchemaError(f"missing required schema child {child_path}")
        if not pa.types.is_int32(children[name]):
            raise VagueSchemaError(
                f"incorrect type for {child_path}: expected int32, got {children[name]}"
            )


def _matches_type_kind(field_type: Any, kind: str, *, path: str = "") -> bool:
    import pyarrow as pa

    if kind == "string":
        return _is_string_type(field_type)
    if kind == "list_string":
        return _is_list_of(field_type, _is_string_type)
    if kind == "list_list_float32":
        return _is_list_of(
            field_type,
            lambda inner: _is_list_of(inner, pa.types.is_float32),
        )
    if kind == "img_size_struct":
        try:
            _validate_img_size_struct(field_type, path or "img_size")
            return True
        except VagueSchemaError:
            return False
    if kind == "rating_struct":
        try:
            _validate_rating_struct(field_type, path or "rating")
            return True
        except VagueSchemaError:
            return False
    raise ValueError(f"unknown schema kind {kind!r}")


def _validate_struct_children(
    struct_type: Any,
    children: tuple[tuple[str, str], ...],
    *,
    path: str,
) -> None:
    import pyarrow as pa

    if not pa.types.is_struct(struct_type):
        raise VagueSchemaError(f"expected struct for {path}, got {struct_type}")

    present = {field.name: field.type for field in struct_type}
    for child_name, child_kind in children:
        child_path = f"{path}.{child_name}"
        if child_name not in present:
            raise VagueSchemaError(f"missing required schema child {child_path}")
        child_type = present[child_name]
        if child_kind == "img_size_struct":
            _validate_img_size_struct(child_type, child_path)
            continue
        if child_kind == "rating_struct":
            _validate_rating_struct(child_type, child_path)
            continue
        if not _matches_type_kind(child_type, child_kind):
            raise VagueSchemaError(
                f"incorrect type for {child_path}: expected {child_kind}, got {child_type}"
            )


def validate_parquet_schema(schema: Any) -> None:
    """Validate required top-level Parquet columns and exact nested layout."""
    names = set(schema.names)
    missing = [name for name in PROJECTED_COLUMNS if name not in names]
    if missing:
        raise VagueSchemaError(f"missing required Parquet columns: {missing}")

    for name in PROJECTED_COLUMNS:
        field_type = schema.field(name).type
        if name == "mcq":
            _validate_struct_children(field_type, MCQ_SCHEMA_CHILDREN, path="mcq")
            continue
        if name == "meta":
            _validate_struct_children(field_type, META_SCHEMA_CHILDREN, path="meta")
            continue
        if not _is_string_type(field_type):
            raise VagueSchemaError(f"expected string for {name!r}, got {field_type}")


def validate_mcq_ordering(ordering: Any) -> str | None:
    """Return quarantine reason when ordering is invalid, else ``None``."""
    if not isinstance(ordering, list):
        return "invalid_mcq_ordering"
    if len(ordering) != 4:
        return "invalid_mcq_ordering"
    if len(set(ordering)) != 4:
        return "invalid_mcq_ordering"
    if set(ordering) != VALID_MCQ_ORDERING_LETTERS:
        return "invalid_mcq_ordering"
    return None


def _row_dict(table: Any, row_index: int) -> dict[str, Any]:
    return {name: table.column(name)[row_index].as_py() for name in PROJECTED_COLUMNS}


def _mapping_notes() -> str:
    return (
        "VAGUE record: command=indirect; scene_context=meta.caption; "
        "resolved_interpretation=mcq.1_correct; intent=solution triplet; "
        "slots parsed deterministically from solution. Project ambiguity taxonomy "
        "abstained. candidate_interpretations preserve semantic MCQ options in "
        "canonical key order. Complete record is weak-mapped "
        "(annotation_status=weak_mapped, label_confidence=weak_derived). "
        "image.bytes never read or serialized."
    )


def _candidate_interpretations(mcq: dict[str, Any]) -> list[CandidateInterpretation]:
    candidates: list[CandidateInterpretation] = []
    for key in MCQ_OPTION_KEYS:
        text = _clean_str(mcq.get(key)).strip()
        candidates.append(CandidateInterpretation(text=text))
    return candidates


def _source_metadata(row: dict[str, Any], row_index: int) -> dict[str, Any]:
    return {
        "image_name": row.get("image_name"),
        "direct": row.get("direct"),
        "indirect": row.get("indirect"),
        "solution": row.get("solution"),
        "mcq": row.get("mcq"),
        "meta": row.get("meta"),
        "row_index": row_index,
    }


def _quarantine_entry(
    *,
    image_name: str,
    row_index: int,
    row: dict[str, Any],
    reason: str,
    details: str,
) -> dict[str, Any]:
    return {
        "image_name": image_name,
        "row_index": row_index,
        "source_id": image_name if image_name else None,
        "reason": reason,
        "details": details,
        "source_row": _source_metadata(row, row_index),
    }


def _build_record(row: dict[str, Any], row_index: int, image_name: str) -> CanonicalRecord:
    mcq = row.get("mcq") or {}
    solution_raw = _clean_str(row.get("solution"))
    slots, _ = parse_solution_triplet(solution_raw)
    assert slots is not None

    return CanonicalRecord(
        id=f"vague:{image_name}",
        record_class=RecordClass.SOURCE_CONVERTED,
        source_dataset=SOURCE_DATASET,
        source_id=image_name,
        original_split=ORIGINAL_SPLIT,
        group_id=None,
        split_status=SplitStatus.TRAIN,
        command=_clean_str(row.get("indirect")).strip(),
        scene_context=_clean_str((row.get("meta") or {}).get("caption")).strip() or None,
        dialogue_history=[],
        capability_context=None,
        candidate_interpretations=_candidate_interpretations(mcq),
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
        gold_clarification_question=None,
        clarification_subtype=None,
        resolved_interpretation=_clean_str(mcq.get("1_correct")).strip(),
        intent=solution_raw,
        slots=slots,
        annotation_status=AnnotationStatus.WEAK_MAPPED,
        label_confidence=LabelConfidence.WEAK_DERIVED,
        label_eligibility=LabelEligibility(intent_slots=True, context_benefit=True),
        mapping_version=MAPPING_VERSION,
        source_license=SOURCE_LICENSE,
        mapping_notes=_mapping_notes(),
        source_metadata=_source_metadata(row, row_index),
        schema_version=CANONICAL_SCHEMA_VERSION,
    )


def convert_file(source_path: str | Path) -> ConversionResult:
    """Convert the authoritative VAGUE Parquet shard into canonical records."""
    _require_pyarrow()
    import pyarrow.parquet as pq

    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(f"missing authoritative Parquet file: {source}")

    parquet_file = pq.ParquetFile(source)
    validate_parquet_schema(parquet_file.schema_arrow)
    metadata_rows = parquet_file.metadata.num_rows if parquet_file.metadata else 0

    records: list[CanonicalRecord] = []
    quarantine: list[dict[str, Any]] = []
    skipped = 0
    skip_reasons: dict[str, int] = {}
    quarantine_reasons: dict[str, int] = {}
    seen_image_names: set[str] = set()
    rows_by_subcorpus: dict[str, int] = {"vcr": 0, "ego4d": 0}
    source_rows_read = 0
    global_row_index = 0

    for row_group_index in range(parquet_file.metadata.num_row_groups):
        table = parquet_file.read_row_group(row_group_index, columns=list(PROJECTED_COLUMNS))
        for local_index in range(table.num_rows):
            row = _row_dict(table, local_index)
            row_index = global_row_index
            global_row_index += 1
            source_rows_read += 1

            image_name = _clean_str(row.get("image_name")).strip()

            if not image_name:
                quarantine.append(
                    _quarantine_entry(
                        image_name="",
                        row_index=row_index,
                        row=row,
                        reason="missing_source_id",
                        details="empty image_name",
                    )
                )
                quarantine_reasons["missing_source_id"] = (
                    quarantine_reasons.get("missing_source_id", 0) + 1
                )
                continue

            _register_image_name(image_name, seen_image_names)

            if not _clean_str(row.get("indirect")).strip():
                quarantine.append(
                    _quarantine_entry(
                        image_name=image_name,
                        row_index=row_index,
                        row=row,
                        reason="missing_command",
                        details="empty indirect",
                    )
                )
                quarantine_reasons["missing_command"] = (
                    quarantine_reasons.get("missing_command", 0) + 1
                )
                continue

            mcq = row.get("mcq") or {}
            if not _clean_str(mcq.get("1_correct")).strip():
                quarantine.append(
                    _quarantine_entry(
                        image_name=image_name,
                        row_index=row_index,
                        row=row,
                        reason="missing_gold_interpretation",
                        details="empty mcq.1_correct",
                    )
                )
                quarantine_reasons["missing_gold_interpretation"] = (
                    quarantine_reasons.get("missing_gold_interpretation", 0) + 1
                )
                continue

            solution_raw = _clean_str(row.get("solution"))
            if not solution_raw:
                quarantine.append(
                    _quarantine_entry(
                        image_name=image_name,
                        row_index=row_index,
                        row=row,
                        reason="missing_solution",
                        details="empty solution",
                    )
                )
                quarantine_reasons["missing_solution"] = (
                    quarantine_reasons.get("missing_solution", 0) + 1
                )
                continue

            slots, triplet_reason = parse_solution_triplet(solution_raw)
            if triplet_reason is not None:
                quarantine.append(
                    _quarantine_entry(
                        image_name=image_name,
                        row_index=row_index,
                        row=row,
                        reason=triplet_reason,
                        details=f"solution={solution_raw!r}",
                    )
                )
                quarantine_reasons[triplet_reason] = quarantine_reasons.get(triplet_reason, 0) + 1
                continue

            caption = _clean_str((row.get("meta") or {}).get("caption")).strip()
            if not caption:
                quarantine.append(
                    _quarantine_entry(
                        image_name=image_name,
                        row_index=row_index,
                        row=row,
                        reason="missing_scene_caption",
                        details="empty meta.caption",
                    )
                )
                quarantine_reasons["missing_scene_caption"] = (
                    quarantine_reasons.get("missing_scene_caption", 0) + 1
                )
                continue

            for key in MCQ_OPTION_KEYS:
                if not _clean_str(mcq.get(key)).strip():
                    quarantine.append(
                        _quarantine_entry(
                            image_name=image_name,
                            row_index=row_index,
                            row=row,
                            reason="missing_mcq_option",
                            details=f"empty mcq.{key}",
                        )
                    )
                    quarantine_reasons["missing_mcq_option"] = (
                        quarantine_reasons.get("missing_mcq_option", 0) + 1
                    )
                    break
            else:
                ordering_reason = validate_mcq_ordering(mcq.get("ordering"))
                if ordering_reason is not None:
                    quarantine.append(
                        _quarantine_entry(
                            image_name=image_name,
                            row_index=row_index,
                            row=row,
                            reason=ordering_reason,
                            details=f"ordering={mcq.get('ordering')!r}",
                        )
                    )
                    quarantine_reasons[ordering_reason] = (
                        quarantine_reasons.get(ordering_reason, 0) + 1
                    )
                    continue

                record = _build_record(row, row_index, image_name)
                try:
                    validate_canonical_record(record)
                except Exception as exc:  # noqa: BLE001
                    quarantine.append(
                        _quarantine_entry(
                            image_name=image_name,
                            row_index=row_index,
                            row=row,
                            reason="schema_validation_failed",
                            details=str(exc),
                        )
                    )
                    quarantine_reasons["schema_validation_failed"] = (
                        quarantine_reasons.get("schema_validation_failed", 0) + 1
                    )
                    continue

                records.append(record)
                subcorpus = _subcorpus(image_name)
                rows_by_subcorpus[subcorpus] = rows_by_subcorpus.get(subcorpus, 0) + 1

    if source_rows_read != metadata_rows:
        raise VagueConversionError(
            f"parser row count {source_rows_read} != metadata row count {metadata_rows}"
        )

    records.sort(key=lambda item: int((item.source_metadata or {}).get("row_index", 0)))

    output_ids = [record.id for record in records]
    if len(output_ids) != len(set(output_ids)):
        duplicate_id = next(item for item in output_ids if output_ids.count(item) > 1)
        raise VagueConversionError(f"duplicate output id {duplicate_id!r}")

    summary = {
        "converter": SOURCE_DATASET,
        "mapping_version": MAPPING_VERSION,
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "source_path": repo_relative_path(source),
        "source_sha256": streaming_sha256(source),
        "metadata_row_count": metadata_rows,
        "source_rows_read": source_rows_read,
        "rows_converted": len(records),
        "rows_skipped": skipped,
        "rows_quarantined": len(quarantine),
        "skip_reasons": dict(sorted(skip_reasons.items())),
        "quarantine_reasons": dict(sorted(quarantine_reasons.items())),
        "output_ids_unique": len(set(output_ids)),
        "rows_by_subcorpus": dict(sorted(rows_by_subcorpus.items())),
        "candidate_interpretations_per_record": 4,
        "projected_columns": list(PROJECTED_COLUMNS),
        "image_bytes_read": False,
        "ordering": ORDERING,
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
    """Convert VAGUE and write canonical, quarantine, and summary artefacts."""
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


def default_raw_source(start: Path | None = None) -> Path:
    from ambiguity_manager.paths import ProjectPaths

    return ProjectPaths.from_repo_root(start).data_raw / AUTHORITATIVE_RELATIVE
