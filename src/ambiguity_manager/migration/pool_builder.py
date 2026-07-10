"""Rebuild schema v2 weak pools from migrated interim canonical outputs."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ambiguity_manager.data_audit.readers import streaming_sha256
from ambiguity_manager.io_guard import resolve_writable_path
from ambiguity_manager.paths import ProjectPaths, repo_relative_path
from ambiguity_manager.schema.v2.jsonl import read_canonical_jsonl_v2, write_canonical_jsonl_v2
from ambiguity_manager.schema.v2.records import CanonicalRecordV2, canonical_record_v2_to_dict

MIGRATION_BUILDER_VERSION = "schema_v2_pool-1.0.0"
MANIFEST_SCHEMA_VERSION = "2.0.0"

PRIMARY_DATASET_ORDER = (
  "ambik",
  "indirect_requests",
  "codraw_icr_v2",
  "vague",
  "clara",
)
AUXILIARY_DATASET_ORDER = ("clariq",)
ALL_DATASET_ORDER = PRIMARY_DATASET_ORDER + AUXILIARY_DATASET_ORDER

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


class SchemaV2PoolBuildError(RuntimeError):
  """Raised when v2 weak-pool validation or build invariants fail."""


@dataclass(frozen=True)
class DatasetV2InputSpec:
  dataset_id: str
  canonical_path: Path


@dataclass(frozen=True)
class SchemaV2PoolOutputSpec:
  primary_path: Path
  auxiliary_path: Path
  membership_path: Path
  manifest_path: Path
  summary_path: Path


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


def production_spec(root: Path | None = None) -> tuple[list[DatasetV2InputSpec], SchemaV2PoolOutputSpec]:
  paths = ProjectPaths.from_repo_root(root)
  inputs = [
    DatasetV2InputSpec(
      dataset_id=dataset_id,
      canonical_path=paths.data_interim / "schema_v2" / dataset_id / f"{dataset_id}_canonical.jsonl",
    )
    for dataset_id in ALL_DATASET_ORDER
  ]
  pool_dir = paths.data_processed / "schema_v2" / "weak_pool"
  outputs = SchemaV2PoolOutputSpec(
    primary_path=pool_dir / "weak_pool_canonical.jsonl",
    auxiliary_path=pool_dir / "weak_pool_auxiliary.jsonl",
    membership_path=pool_dir / "weak_pool_membership.jsonl",
    manifest_path=paths.outputs / "manifests" / "schema_v2_weak_pool_manifest.json",
    summary_path=paths.outputs / "metrics" / "schema_v2_migration_summary.json",
  )
  return inputs, outputs


def _deterministic_json(data: Any) -> str:
  return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _ordered_pool_records(
  datasets: list[tuple[str, list[CanonicalRecordV2]]],
  order: tuple[str, ...],
) -> list[CanonicalRecordV2]:
  by_id: dict[str, list[CanonicalRecordV2]] = {dataset_id: records for dataset_id, records in datasets}
  ordered: list[CanonicalRecordV2] = []
  for dataset_id in order:
    records = sorted(by_id.get(dataset_id, []), key=lambda item: item.id)
    ordered.extend(records)
  return ordered


def _membership_rows(
  primary_records: list[CanonicalRecordV2],
  auxiliary_records: list[CanonicalRecordV2],
) -> list[MembershipRow]:
  rows: list[MembershipRow] = []
  for record in primary_records:
    role = DATASET_ROLE_CONFIG[record.source_dataset]
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
  for record in auxiliary_records:
    role = DATASET_ROLE_CONFIG[record.source_dataset]
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
  return sorted(rows, key=lambda row: (row.physical_pool, row.source_dataset, row.id))


def _assert_accounting(
  primary_records: list[CanonicalRecordV2],
  auxiliary_records: list[CanonicalRecordV2],
  membership_rows: list[MembershipRow],
) -> dict[str, bool]:
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
    raise SchemaV2PoolBuildError(f"accounting invariant failed: {checks}")
  return checks


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


def build_schema_v2_pools(
  inputs: list[DatasetV2InputSpec],
  outputs: SchemaV2PoolOutputSpec,
) -> dict[str, Any]:
  spec_by_id = {spec.dataset_id: spec for spec in inputs}
  missing = [dataset_id for dataset_id in ALL_DATASET_ORDER if dataset_id not in spec_by_id]
  if missing:
    raise SchemaV2PoolBuildError(f"missing dataset specs: {missing}")

  loaded: list[tuple[str, list[CanonicalRecordV2], str]] = []
  global_ids: dict[str, str] = {}
  input_records_by_id: dict[str, dict[str, CanonicalRecordV2]] = {}

  for dataset_id in ALL_DATASET_ORDER:
    spec = spec_by_id[dataset_id]
    if not spec.canonical_path.is_file():
      raise SchemaV2PoolBuildError(f"missing migrated canonical input: {spec.canonical_path}")
    records = read_canonical_jsonl_v2(spec.canonical_path)
    input_sha256 = streaming_sha256(spec.canonical_path)
    input_records_by_id[dataset_id] = {record.id: record for record in records}
    for record in records:
      if record.id in global_ids:
        raise SchemaV2PoolBuildError(
          f"duplicate id across inputs: {record.id!r} ({global_ids[record.id]} and {dataset_id})"
        )
      global_ids[record.id] = dataset_id
      if record.source_dataset != dataset_id:
        raise SchemaV2PoolBuildError(
          f"source_dataset mismatch for {record.id!r}: expected {dataset_id}, got {record.source_dataset}"
        )
      if record.source_dataset == "safe_agent_bench":
        raise SchemaV2PoolBuildError("SafeAgentBench must not appear in schema v2 pools")
    loaded.append((dataset_id, records, input_sha256))

  primary_datasets = [
    (dataset_id, records) for dataset_id, records, _ in loaded if DATASET_ROLE_CONFIG[dataset_id]["physical_pool"] == "primary"
  ]
  auxiliary_datasets = [
    (dataset_id, records) for dataset_id, records, _ in loaded if DATASET_ROLE_CONFIG[dataset_id]["physical_pool"] == "auxiliary"
  ]

  primary_records = _ordered_pool_records(primary_datasets, PRIMARY_DATASET_ORDER)
  auxiliary_records = _ordered_pool_records(auxiliary_datasets, AUXILIARY_DATASET_ORDER)
  membership_rows = _membership_rows(primary_records, auxiliary_records)
  checks = _assert_accounting(primary_records, auxiliary_records, membership_rows)

  for dataset_id, records in input_records_by_id.items():
    pool_records = primary_records if DATASET_ROLE_CONFIG[dataset_id]["physical_pool"] == "primary" else auxiliary_records
    output_by_id = {record.id: record for record in pool_records}
    for record_id, input_record in records.items():
      output_record = output_by_id[record_id]
      if canonical_record_v2_to_dict(input_record) != canonical_record_v2_to_dict(output_record):
        raise SchemaV2PoolBuildError(f"record preservation failed for {record_id}")

  by_dataset = {dataset_id: len(records) for dataset_id, records, _ in loaded}
  summary_payload = {
    "summary_schema_version": MANIFEST_SCHEMA_VERSION,
    "builder_version": MIGRATION_BUILDER_VERSION,
    "counts": {
      "primary_pool": len(primary_records),
      "auxiliary_pool": len(auxiliary_records),
      "membership_rows": len(membership_rows),
      "global_unique_ids": len({row.id for row in membership_rows}),
      "by_dataset": by_dataset,
    },
    "accounting_checks": checks,
  }

  manifest_inputs = [
    {
      "dataset_id": dataset_id,
      "dataset_role": DATASET_ROLE_CONFIG[dataset_id]["dataset_role"],
      "core_pool_status": DATASET_ROLE_CONFIG[dataset_id]["core_pool_status"],
      "physical_pool": DATASET_ROLE_CONFIG[dataset_id]["physical_pool"],
      "canonical_input_path": repo_relative_path(spec_by_id[dataset_id].canonical_path),
      "canonical_input_sha256": input_sha256,
      "canonical_input_record_count": len(records),
      "mapping_version": DATASET_ROLE_CONFIG[dataset_id]["mapping_version"],
    }
    for dataset_id, records, input_sha256 in loaded
  ]

  manifest_payload = {
    "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
    "canonical_schema_version": "2.0.0",
    "builder_version": MIGRATION_BUILDER_VERSION,
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
    "accounting_checks": checks,
  }

  write_canonical_jsonl_v2(outputs.primary_path, primary_records)
  write_canonical_jsonl_v2(outputs.auxiliary_path, auxiliary_records)
  _write_membership_jsonl(outputs.membership_path, membership_rows)

  output_hashes = {
    "primary_pool_sha256": streaming_sha256(outputs.primary_path),
    "auxiliary_pool_sha256": streaming_sha256(outputs.auxiliary_path),
    "membership_sha256": streaming_sha256(outputs.membership_path),
  }
  manifest_payload["outputs"] = {**manifest_payload["outputs"], **output_hashes}
  manifest_payload["input_sha256"] = {item["dataset_id"]: item["canonical_input_sha256"] for item in manifest_inputs}
  _write_json(outputs.manifest_path, manifest_payload)
  _write_json(outputs.summary_path, summary_payload)

  return {
    "primary_count": len(primary_records),
    "auxiliary_count": len(auxiliary_records),
    "membership_count": len(membership_rows),
    "global_unique_id_count": len(membership_rows),
    "per_dataset_counts": by_dataset,
    "accounting_checks": checks,
    "output_sha256": output_hashes,
    "paths": {
      "primary": repo_relative_path(outputs.primary_path),
      "auxiliary": repo_relative_path(outputs.auxiliary_path),
      "membership": repo_relative_path(outputs.membership_path),
      "manifest": repo_relative_path(outputs.manifest_path),
      "summary": repo_relative_path(outputs.summary_path),
    },
  }
