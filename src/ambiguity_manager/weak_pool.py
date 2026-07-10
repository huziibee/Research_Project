"""Weak labelled pool builder (T09).

Combines validated T03–T08 canonical JSONL outputs into physically separate
primary (robot) and auxiliary pools plus a deterministic membership index.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ambiguity_manager.data_audit.readers import streaming_sha256
from ambiguity_manager.io_guard import resolve_writable_path
from ambiguity_manager.paths import ProjectPaths, repo_relative_path
from ambiguity_manager.schema.errors import SchemaValidationError
from ambiguity_manager.schema.jsonl import write_canonical_jsonl
from ambiguity_manager.schema.records import CanonicalRecord, canonical_record_to_dict
from ambiguity_manager.schema.taxonomies import RecordClass
from ambiguity_manager.schema.validation import validate_canonical_record
from ambiguity_manager.schema.version import CANONICAL_SCHEMA_VERSION

BUILDER_VERSION = "weak_pool-1.0.0"
MANIFEST_SCHEMA_VERSION = "1.0.0"

PRIMARY_DATASET_ORDER = (
    "ambik",
    "indirect_requests",
    "codraw_icr_v2",
    "vague",
    "clara",
)
AUXILIARY_DATASET_ORDER = ("clariq",)
ALL_DATASET_ORDER = PRIMARY_DATASET_ORDER + AUXILIARY_DATASET_ORDER

PROVENANCE_EXCLUDED_FROM_SEMANTIC_HASH = frozenset(
    {
        "id",
        "source_id",
        "source_dataset",
        "source_metadata",
        "mapping_notes",
        "mapping_version",
        "source_license",
    }
)

DATASET_ROLE_CONFIG: dict[str, dict[str, str]] = {
    "ambik": {
        "dataset_role": "core",
        "core_pool_status": "eligible",
        "physical_pool": "primary",
        "mapping_version": "ambik-1.0.0",
    },
    "indirect_requests": {
        "dataset_role": "core",
        "core_pool_status": "eligible",
        "physical_pool": "primary",
        "mapping_version": "indirect_requests-1.0.0",
    },
    "codraw_icr_v2": {
        "dataset_role": "conditional_core",
        "core_pool_status": "conditional_pending",
        "physical_pool": "primary",
        "mapping_version": "codraw_icr_v2-1.0.0",
    },
    "vague": {
        "dataset_role": "conditional_core",
        "core_pool_status": "conditional_pending",
        "physical_pool": "primary",
        "mapping_version": "vague-1.0.0",
    },
    "clara": {
        "dataset_role": "conditional_core",
        "core_pool_status": "conditional_pending",
        "physical_pool": "primary",
        "mapping_version": "clara-1.0.0",
    },
    "clariq": {
        "dataset_role": "auxiliary",
        "core_pool_status": "ineligible",
        "physical_pool": "auxiliary",
        "mapping_version": "clariq-1.0.0",
    },
}


class WeakPoolBuildError(RuntimeError):
    """Raised when weak-pool validation or build invariants fail."""


@dataclass(frozen=True)
class DatasetInputSpec:
    dataset_id: str
    canonical_path: Path
    summary_path: Path


@dataclass(frozen=True)
class WeakPoolOutputSpec:
    primary_path: Path
    auxiliary_path: Path
    membership_path: Path
    manifest_path: Path
    summary_path: Path


@dataclass
class LoadedDataset:
    spec: DatasetInputSpec
    records: list[CanonicalRecord]
    input_sha256: str
    summary: dict[str, Any]
    role: dict[str, str]


@dataclass
class MembershipRow:
    id: str
    source_dataset: str
    dataset_role: str
    core_pool_status: str
    physical_pool: str
    included: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_dataset": self.source_dataset,
            "dataset_role": self.dataset_role,
            "core_pool_status": self.core_pool_status,
            "physical_pool": self.physical_pool,
            "included": self.included,
        }


def production_spec(root: Path | None = None) -> tuple[list[DatasetInputSpec], WeakPoolOutputSpec]:
    paths = ProjectPaths.from_repo_root(root)
    inputs = [
        DatasetInputSpec(
            dataset_id=dataset_id,
            canonical_path=paths.data_interim / dataset_id / f"{dataset_id}_canonical.jsonl",
            summary_path=paths.outputs / "metrics" / f"{dataset_id}_conversion_summary.json",
        )
        for dataset_id in ALL_DATASET_ORDER
    ]
    pool_dir = paths.data_processed / "weak_pool"
    outputs = WeakPoolOutputSpec(
        primary_path=pool_dir / "weak_pool_canonical.jsonl",
        auxiliary_path=pool_dir / "weak_pool_auxiliary.jsonl",
        membership_path=pool_dir / "weak_pool_membership.jsonl",
        manifest_path=paths.outputs / "manifests" / "weak_pool_manifest.json",
        summary_path=paths.outputs / "metrics" / "weak_pool_summary.json",
    )
    return inputs, outputs


def _deterministic_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _integrity_hash(record: CanonicalRecord) -> str:
    return _sha256_text(_deterministic_json(canonical_record_to_dict(record)))


def _semantic_payload_hash(record: CanonicalRecord) -> str:
    payload = canonical_record_to_dict(record)
    for key in PROVENANCE_EXCLUDED_FROM_SEMANTIC_HASH:
        payload.pop(key, None)
    return _sha256_text(_deterministic_json(payload))


def _normalize_command(command: str) -> str:
    return " ".join(command.strip().lower().split())


def _load_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise WeakPoolBuildError(f"missing conversion summary: {path}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _validate_summary_path(summary: dict[str, Any], canonical_path: Path, dataset_id: str) -> None:
    reported = summary.get("output_path")
    if not isinstance(reported, str) or not reported.strip():
        raise WeakPoolBuildError(f"{dataset_id}: summary missing output_path")
    root = ProjectPaths.from_repo_root().root.resolve()

    def as_repo_relative(path: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            return resolved.as_posix()

    actual = as_repo_relative(canonical_path)
    reported_path = Path(reported)
    if not reported_path.is_absolute():
        reported_path = root / reported_path
    expected = as_repo_relative(reported_path)
    if expected != actual:
        raise WeakPoolBuildError(
            f"{dataset_id}: summary output_path mismatch ({expected!r} != {actual!r})"
        )


def _validate_mapping_version(
    records: list[CanonicalRecord],
    summary: dict[str, Any],
    dataset_id: str,
    expected_mapping_version: str,
) -> None:
    summary_version = summary.get("mapping_version")
    if summary_version != expected_mapping_version:
        raise WeakPoolBuildError(
            f"{dataset_id}: summary mapping_version {summary_version!r} != expected {expected_mapping_version!r}"
        )
    record_versions = Counter(record.mapping_version for record in records)
    if len(record_versions) != 1:
        raise WeakPoolBuildError(f"{dataset_id}: inconsistent record mapping_version distribution {dict(record_versions)}")
    if next(iter(record_versions)) != expected_mapping_version:
        raise WeakPoolBuildError(
            f"{dataset_id}: record mapping_version {next(iter(record_versions))!r} != expected {expected_mapping_version!r}"
        )


def _parse_canonical_file(path: Path, dataset_id: str) -> list[CanonicalRecord]:
    if not path.is_file():
        raise WeakPoolBuildError(f"missing canonical input: {path}")
    records: list[CanonicalRecord] = []
    seen_ids: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                raise WeakPoolBuildError(f"{dataset_id}: blank JSONL line at {line_number}")
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise WeakPoolBuildError(f"{dataset_id}: malformed JSON at line {line_number}") from exc
            try:
                record = validate_canonical_record(payload)
            except SchemaValidationError as exc:
                raise WeakPoolBuildError(f"{dataset_id}: invalid canonical record at line {line_number}: {exc}") from exc
            if record.schema_version != CANONICAL_SCHEMA_VERSION:
                raise WeakPoolBuildError(
                    f"{dataset_id}: unsupported schema_version {record.schema_version!r} at line {line_number}"
                )
            if record.record_class != RecordClass.SOURCE_CONVERTED:
                raise WeakPoolBuildError(
                    f"{dataset_id}: record_class {record.record_class!r} at line {line_number}"
                )
            if record.source_dataset != dataset_id:
                raise WeakPoolBuildError(
                    f"{dataset_id}: source_dataset {record.source_dataset!r} at line {line_number}"
                )
            if not record.id.strip():
                raise WeakPoolBuildError(f"{dataset_id}: empty id at line {line_number}")
            if record.source_id is None or not str(record.source_id).strip():
                raise WeakPoolBuildError(f"{dataset_id}: empty source_id at line {line_number}")
            if record.id in seen_ids:
                raise WeakPoolBuildError(f"{dataset_id}: duplicate id {record.id!r} within input")
            seen_ids.add(record.id)
            records.append(record)
    return records


def load_dataset(spec: DatasetInputSpec) -> LoadedDataset:
    role = DATASET_ROLE_CONFIG[spec.dataset_id]
    records = _parse_canonical_file(spec.canonical_path, spec.dataset_id)
    summary = _load_summary(spec.summary_path)
    _validate_summary_path(summary, spec.canonical_path, spec.dataset_id)
    rows_converted = summary.get("rows_converted")
    if rows_converted != len(records):
        raise WeakPoolBuildError(
            f"{spec.dataset_id}: summary rows_converted {rows_converted!r} != parsed count {len(records)}"
        )
    _validate_mapping_version(records, summary, spec.dataset_id, role["mapping_version"])
    return LoadedDataset(
        spec=spec,
        records=records,
        input_sha256=streaming_sha256(spec.canonical_path),
        summary=summary,
        role=role,
    )


def _sort_records(records: Iterable[CanonicalRecord]) -> list[CanonicalRecord]:
    return sorted(records, key=lambda record: record.id)


def _ordered_pool_records(loaded: list[LoadedDataset], dataset_order: tuple[str, ...]) -> list[CanonicalRecord]:
    by_dataset = {dataset.spec.dataset_id: _sort_records(dataset.records) for dataset in loaded}
    ordered: list[CanonicalRecord] = []
    for dataset_id in dataset_order:
        ordered.extend(by_dataset.get(dataset_id, []))
    return ordered


def _membership_rows(primary_records: list[CanonicalRecord], auxiliary_records: list[CanonicalRecord], loaded: list[LoadedDataset]) -> list[MembershipRow]:
    role_by_dataset = {dataset.spec.dataset_id: dataset.role for dataset in loaded}
    rows: list[MembershipRow] = []
    for record in primary_records + auxiliary_records:
        role = role_by_dataset[record.source_dataset]
        rows.append(
            MembershipRow(
                id=record.id,
                source_dataset=record.source_dataset,
                dataset_role=role["dataset_role"],
                core_pool_status=role["core_pool_status"],
                physical_pool=role["physical_pool"],
                included=True,
            )
        )
    return rows


def _count_distribution(records: list[CanonicalRecord], field_name: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for record in records:
        value = getattr(record, field_name)
        if hasattr(value, "value"):
            value = value.value
        counter[str(value)] += 1
    return dict(sorted(counter.items()))


def _label_eligibility_counts(records: list[CanonicalRecord]) -> dict[str, int]:
    counts = {name: 0 for name in records[0].label_eligibility.to_dict().keys()} if records else {}
    for record in records:
        for name, enabled in record.label_eligibility.to_dict().items():
            if enabled:
                counts[name] += 1
    return counts


def _ambiguity_type_counts(records: list[CanonicalRecord]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for record in records:
        for item in record.ambiguity_types:
            counter[item.value] += 1
    return dict(sorted(counter.items()))


def _overlap_analysis(records: list[CanonicalRecord]) -> dict[str, Any]:
    integrity_hashes: Counter[str] = Counter()
    semantic_hashes: Counter[str] = Counter()
    command_hashes: Counter[str] = Counter()
    norm_command_hashes: Counter[str] = Counter()
    command_scene_hashes: Counter[str] = Counter()
    norm_command_datasets: dict[str, set[str]] = defaultdict(set)
    group_ids: Counter[str] = Counter()

    for record in records:
        integrity_hashes[_integrity_hash(record)] += 1
        semantic_hashes[_semantic_payload_hash(record)] += 1
        command_hashes[record.command] += 1
        normalized = _normalize_command(record.command)
        norm_command_hashes[normalized] += 1
        norm_command_datasets[normalized].add(record.source_dataset)
        scene_key = _deterministic_json([normalized, record.scene_context])
        command_scene_hashes[scene_key] += 1
        if record.group_id:
            group_ids[record.group_id] += 1

    def duplicate_groups(counter: Counter[str]) -> int:
        return sum(1 for count in counter.values() if count > 1)

    return {
        "integrity_duplicate_groups": duplicate_groups(integrity_hashes),
        "semantic_payload_duplicate_groups": duplicate_groups(semantic_hashes),
        "exact_command_duplicate_groups": duplicate_groups(command_hashes),
        "normalized_command_duplicate_groups": duplicate_groups(norm_command_hashes),
        "command_scene_context_duplicate_groups": duplicate_groups(command_scene_hashes),
        "cross_dataset_normalized_command_overlaps": sum(
            1 for datasets in norm_command_datasets.values() if len(datasets) > 1
        ),
        "repeated_non_null_group_id_values": sum(1 for count in group_ids.values() if count > 1),
    }


def _feature_counts(records: list[CanonicalRecord]) -> dict[str, int]:
    return {
        "records_with_group_id": sum(1 for record in records if record.group_id),
        "records_with_clarification_target": sum(1 for record in records if record.gold_clarification_question),
        "records_with_resolved_interpretation": sum(1 for record in records if record.resolved_interpretation),
        "records_with_candidate_interpretations": sum(
            1 for record in records if record.candidate_interpretations
        ),
    }


def _aggregate_summary(
    primary_records: list[CanonicalRecord],
    auxiliary_records: list[CanonicalRecord],
    membership_rows: list[MembershipRow],
    overlap: dict[str, Any],
) -> dict[str, Any]:
    all_records = primary_records + auxiliary_records
    by_dataset = {
        dataset_id: sum(1 for row in membership_rows if row.source_dataset == dataset_id)
        for dataset_id in ALL_DATASET_ORDER
    }
    by_role = {
        role: sum(1 for row in membership_rows if row.dataset_role == role)
        for role in sorted({row.dataset_role for row in membership_rows})
    }
    return {
        "summary_schema_version": "1.0.0",
        "builder_version": BUILDER_VERSION,
        "counts": {
            "primary_pool": len(primary_records),
            "auxiliary_pool": len(auxiliary_records),
            "membership_rows": len(membership_rows),
            "global_unique_ids": len({row.id for row in membership_rows}),
            "by_dataset": by_dataset,
            "by_dataset_role": by_role,
            "by_core_pool_status": dict(
                sorted(Counter(row.core_pool_status for row in membership_rows).items())
            ),
        },
        "distributions": {
            "primary": {
                "original_split": _count_distribution(primary_records, "original_split"),
                "split_status": _count_distribution(primary_records, "split_status"),
                "annotation_status": _count_distribution(primary_records, "annotation_status"),
                "label_confidence": _count_distribution(primary_records, "label_confidence"),
                "ambiguity_present": _count_distribution(primary_records, "ambiguity_present"),
                "ambiguity_types": _ambiguity_type_counts(primary_records),
                "recommended_strategy": _count_distribution(primary_records, "recommended_strategy"),
                "risk_relevant": _count_distribution(primary_records, "risk_relevant"),
                "risk_level": _count_distribution(primary_records, "risk_level"),
                "capability_status": _count_distribution(primary_records, "capability_status"),
                "label_eligibility": _label_eligibility_counts(primary_records),
                **_feature_counts(primary_records),
            },
            "auxiliary": {
                "original_split": _count_distribution(auxiliary_records, "original_split"),
                "split_status": _count_distribution(auxiliary_records, "split_status"),
                "annotation_status": _count_distribution(auxiliary_records, "annotation_status"),
                "label_confidence": _count_distribution(auxiliary_records, "label_confidence"),
                "ambiguity_present": _count_distribution(auxiliary_records, "ambiguity_present"),
                "ambiguity_types": _ambiguity_type_counts(auxiliary_records),
                "recommended_strategy": _count_distribution(auxiliary_records, "recommended_strategy"),
                "risk_relevant": _count_distribution(auxiliary_records, "risk_relevant"),
                "risk_level": _count_distribution(auxiliary_records, "risk_level"),
                "capability_status": _count_distribution(auxiliary_records, "capability_status"),
                "label_eligibility": _label_eligibility_counts(auxiliary_records),
                **_feature_counts(auxiliary_records),
            },
            "combined": {
                "original_split": _count_distribution(all_records, "original_split"),
                "split_status": _count_distribution(all_records, "split_status"),
                "annotation_status": _count_distribution(all_records, "annotation_status"),
                "label_confidence": _count_distribution(all_records, "label_confidence"),
                "ambiguity_present": _count_distribution(all_records, "ambiguity_present"),
                "ambiguity_types": _ambiguity_type_counts(all_records),
                "recommended_strategy": _count_distribution(all_records, "recommended_strategy"),
                "risk_relevant": _count_distribution(all_records, "risk_relevant"),
                "risk_level": _count_distribution(all_records, "risk_level"),
                "capability_status": _count_distribution(all_records, "capability_status"),
                "label_eligibility": _label_eligibility_counts(all_records),
                **_feature_counts(all_records),
            },
        },
        "overlap_analysis": overlap,
        "weak_pool_notice": "This weak labelled pool is not the final gold evaluation benchmark.",
    }


def _write_membership_jsonl(path: Path, rows: list[MembershipRow]) -> None:
    target = resolve_writable_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [_deterministic_json(row.to_dict()) for row in rows]
    text = "\n".join(lines) + ("\n" if lines else "")
    target.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    target = resolve_writable_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_deterministic_json(payload) + "\n", encoding="utf-8")


def _read_membership_ids(path: Path) -> list[str]:
    ids: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                raise WeakPoolBuildError(f"blank membership line at {line_number}")
            payload = json.loads(stripped)
            ids.append(str(payload["id"]))
    return ids


def _read_pool_ids(path: Path) -> list[str]:
    ids: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                raise WeakPoolBuildError(f"blank pool line at {line_number}")
            payload = json.loads(stripped)
            ids.append(str(payload["id"]))
    return ids


def _assert_accounting(
    primary_records: list[CanonicalRecord],
    auxiliary_records: list[CanonicalRecord],
    membership_rows: list[MembershipRow],
) -> dict[str, Any]:
    primary_ids = {record.id for record in primary_records}
    auxiliary_ids = {record.id for record in auxiliary_records}
    membership_ids = {row.id for row in membership_rows}
    intersection = primary_ids & auxiliary_ids
    union = primary_ids | auxiliary_ids
    checks = {
        "primary_id_count_equals_record_count": len(primary_ids) == len(primary_records),
        "auxiliary_id_count_equals_record_count": len(auxiliary_ids) == len(auxiliary_records),
        "primary_auxiliary_disjoint": not intersection,
        "membership_equals_union": membership_ids == union,
        "global_unique_ids_equal_membership_rows": len(membership_ids) == len(membership_rows),
    }
    if not all(checks.values()):
        raise WeakPoolBuildError(f"accounting invariant failed: {checks}")
    return checks


def build_weak_pool(
    inputs: list[DatasetInputSpec],
    outputs: WeakPoolOutputSpec,
    *,
    publish: bool = True,
) -> dict[str, Any]:
    ordered_ids = list(ALL_DATASET_ORDER)
    spec_by_id = {spec.dataset_id: spec for spec in inputs}
    missing = [dataset_id for dataset_id in ordered_ids if dataset_id not in spec_by_id]
    if missing:
        raise WeakPoolBuildError(f"missing dataset specs: {missing}")

    loaded = [load_dataset(spec_by_id[dataset_id]) for dataset_id in ordered_ids]
    global_ids: dict[str, str] = {}
    input_records_by_id: dict[str, dict[str, CanonicalRecord]] = {}
    primary_records: list[CanonicalRecord] = []
    auxiliary_records: list[CanonicalRecord] = []

    for dataset in loaded:
        input_records_by_id[dataset.spec.dataset_id] = {record.id: record for record in dataset.records}
        target = primary_records if dataset.role["physical_pool"] == "primary" else auxiliary_records
        target.extend(dataset.records)
        for record in dataset.records:
            if record.id in global_ids:
                raise WeakPoolBuildError(
                    f"duplicate id across inputs: {record.id!r} ({global_ids[record.id]} and {dataset.spec.dataset_id})"
                )
            global_ids[record.id] = dataset.spec.dataset_id

    primary_records = _ordered_pool_records(
        [dataset for dataset in loaded if dataset.role["physical_pool"] == "primary"],
        PRIMARY_DATASET_ORDER,
    )
    auxiliary_records = _ordered_pool_records(
        [dataset for dataset in loaded if dataset.role["physical_pool"] == "auxiliary"],
        AUXILIARY_DATASET_ORDER,
    )
    membership_rows = _membership_rows(primary_records, auxiliary_records, loaded)
    _assert_accounting(primary_records, auxiliary_records, membership_rows)

    overlap = _overlap_analysis(primary_records + auxiliary_records)
    summary_payload = _aggregate_summary(primary_records, auxiliary_records, membership_rows, overlap)

    manifest_inputs = [
        {
            "dataset_id": dataset.spec.dataset_id,
            "dataset_role": dataset.role["dataset_role"],
            "core_pool_status": dataset.role["core_pool_status"],
            "physical_pool": dataset.role["physical_pool"],
            "canonical_input_path": repo_relative_path(dataset.spec.canonical_path),
            "canonical_input_sha256": dataset.input_sha256,
            "canonical_input_record_count": len(dataset.records),
            "conversion_summary_path": repo_relative_path(dataset.spec.summary_path),
            "mapping_version": dataset.role["mapping_version"],
        }
        for dataset in loaded
    ]

    pool_parent = resolve_writable_path(outputs.primary_path.parent)
    pool_parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=".weak_pool_build_", dir=str(pool_parent)))
    temp_paths = {
        "primary": temp_dir / "weak_pool_canonical.jsonl",
        "auxiliary": temp_dir / "weak_pool_auxiliary.jsonl",
        "membership": temp_dir / "weak_pool_membership.jsonl",
        "manifest": temp_dir / "weak_pool_manifest.json",
        "summary": temp_dir / "weak_pool_summary.json",
    }
    final_paths = {
        "primary": resolve_writable_path(outputs.primary_path),
        "auxiliary": resolve_writable_path(outputs.auxiliary_path),
        "membership": resolve_writable_path(outputs.membership_path),
        "manifest": resolve_writable_path(outputs.manifest_path),
        "summary": resolve_writable_path(outputs.summary_path),
    }

    try:
        write_canonical_jsonl(temp_paths["primary"], primary_records)
        write_canonical_jsonl(temp_paths["auxiliary"], auxiliary_records)
        _write_membership_jsonl(temp_paths["membership"], membership_rows)

        manifest_without_hashes = {
            "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
            "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
            "builder_version": BUILDER_VERSION,
            "ordering_policy": "primary_dataset_order_then_id_asc_then_auxiliary_dataset_order_then_id_asc",
            "primary_dataset_order": list(PRIMARY_DATASET_ORDER),
            "auxiliary_dataset_order": list(AUXILIARY_DATASET_ORDER),
            "included_datasets": list(ALL_DATASET_ORDER),
            "excluded_datasets": [
                {
                    "dataset_id": "safe_agent_bench",
                    "reason": "no_approved_canonical_converter_output",
                }
            ],
            "inputs": manifest_inputs,
            "outputs": {
                "primary_pool_path": repo_relative_path(outputs.primary_path),
                "auxiliary_pool_path": repo_relative_path(outputs.auxiliary_path),
                "membership_path": repo_relative_path(outputs.membership_path),
            },
            "counts": summary_payload["counts"],
            "accounting_checks": _assert_accounting(primary_records, auxiliary_records, membership_rows),
            "overlap_analysis": overlap,
        }
        _write_json(temp_paths["manifest"], manifest_without_hashes)
        _write_json(temp_paths["summary"], summary_payload)

        temp_primary_ids = _read_pool_ids(temp_paths["primary"])
        temp_auxiliary_ids = _read_pool_ids(temp_paths["auxiliary"])
        temp_membership_ids = _read_membership_ids(temp_paths["membership"])
        if set(temp_primary_ids) & set(temp_auxiliary_ids):
            raise WeakPoolBuildError("temporary outputs are not disjoint")
        if set(temp_membership_ids) != set(temp_primary_ids) | set(temp_auxiliary_ids):
            raise WeakPoolBuildError("temporary membership does not equal union of pool ids")

        for dataset_id, records in input_records_by_id.items():
            pool_records = primary_records if DATASET_ROLE_CONFIG[dataset_id]["physical_pool"] == "primary" else auxiliary_records
            output_by_id = {record.id: record for record in pool_records}
            for record_id, input_record in records.items():
                output_record = output_by_id[record_id]
                if canonical_record_to_dict(input_record) != canonical_record_to_dict(output_record):
                    raise WeakPoolBuildError(f"record preservation failed for {record_id}")

        output_hashes = {
            "primary_pool_sha256": streaming_sha256(temp_paths["primary"]),
            "auxiliary_pool_sha256": streaming_sha256(temp_paths["auxiliary"]),
            "membership_sha256": streaming_sha256(temp_paths["membership"]),
        }
        manifest_payload = {
            **manifest_without_hashes,
            "outputs": {
                **manifest_without_hashes["outputs"],
                **output_hashes,
            },
            "input_sha256": {item["dataset_id"]: item["canonical_input_sha256"] for item in manifest_inputs},
        }
        _write_json(temp_paths["manifest"], manifest_payload)

        result = {
            "primary_count": len(primary_records),
            "auxiliary_count": len(auxiliary_records),
            "membership_count": len(membership_rows),
            "global_unique_id_count": len(membership_rows),
            "per_dataset_counts": summary_payload["counts"]["by_dataset"],
            "accounting_checks": manifest_payload["accounting_checks"],
            "overlap_analysis": overlap,
            "input_sha256": manifest_payload["input_sha256"],
            "output_sha256": output_hashes,
            "paths": {
                "primary": repo_relative_path(outputs.primary_path),
                "auxiliary": repo_relative_path(outputs.auxiliary_path),
                "membership": repo_relative_path(outputs.membership_path),
                "manifest": repo_relative_path(outputs.manifest_path),
                "summary": repo_relative_path(outputs.summary_path),
            },
        }

        if publish:
            for key in ("primary", "auxiliary", "membership", "manifest", "summary"):
                final_paths[key].parent.mkdir(parents=True, exist_ok=True)
                os.replace(temp_paths[key], final_paths[key])
            result["published"] = True
        else:
            result["published"] = False
            result["temp_paths"] = {key: str(path) for key, path in temp_paths.items()}
        return result
    except Exception:
        raise
    finally:
        for path in temp_paths.values():
            if path.exists():
                path.unlink(missing_ok=True)
        if temp_dir.exists():
            temp_dir.rmdir()
