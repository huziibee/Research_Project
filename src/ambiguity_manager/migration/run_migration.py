"""Schema v2 migration orchestration with atomic publication."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from ambiguity_manager.data_audit.readers import streaming_sha256
from ambiguity_manager.io_guard import resolve_writable_path
from ambiguity_manager.migration.pool_builder import (
  ALL_DATASET_ORDER,
  DatasetV2InputSpec,
  SchemaV2PoolBuildError,
  SchemaV2PoolOutputSpec,
  build_schema_v2_pools,
)
from ambiguity_manager.migration.v1_to_v2 import (
  MIGRATION_VERSION,
  MigrationAccounting,
  MigrationError,
  migrate_v1_dict_to_v2,
)
from ambiguity_manager.paths import ProjectPaths, repo_relative_path
from ambiguity_manager.schema.jsonl import read_canonical_jsonl
from ambiguity_manager.schema.records import canonical_record_to_dict
from ambiguity_manager.schema.v2.jsonl import write_canonical_jsonl_v2
from ambiguity_manager.schema.v2.version import SCHEMA_VERSION

MIGRATION_MANIFEST_SCHEMA_VERSION = "2.0.0"

V1_INTERIM_PATHS = tuple(
  f"data/interim/{dataset_id}/{dataset_id}_canonical.jsonl" for dataset_id in ALL_DATASET_ORDER
)
V1_POOL_PATHS = (
  "data/processed/weak_pool/weak_pool_canonical.jsonl",
  "data/processed/weak_pool/weak_pool_auxiliary.jsonl",
  "data/processed/weak_pool/weak_pool_membership.jsonl",
)

FINAL_RELATIVE_PATHS = (
  *(f"data/interim/schema_v2/{dataset_id}/{dataset_id}_canonical.jsonl" for dataset_id in ALL_DATASET_ORDER),
  "data/processed/schema_v2/weak_pool/weak_pool_canonical.jsonl",
  "data/processed/schema_v2/weak_pool/weak_pool_auxiliary.jsonl",
  "data/processed/schema_v2/weak_pool/weak_pool_membership.jsonl",
  "outputs/manifests/schema_v2_migration_manifest.json",
  "outputs/manifests/schema_v2_weak_pool_manifest.json",
  "outputs/metrics/schema_v2_migration_summary.json",
)

EXPECTED_COUNTS = {
  "ambik": 1000,
  "indirect_requests": 906,
  "codraw_icr_v2": 7034,
  "vague": 1677,
  "clara": 5222,
  "clariq": 8565,
  "primary_pool": 15839,
  "auxiliary_pool": 8565,
  "membership_rows": 24404,
  "global_unique_ids": 24404,
}


class SchemaV2MigrationError(RuntimeError):
  """Raised when schema v2 migration fails."""


def _deterministic_json(data: Any) -> str:
  return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_protected_inputs(root: Path) -> dict[str, str]:
  hashes: dict[str, str] = {}
  for relative in V1_INTERIM_PATHS + V1_POOL_PATHS:
    path = root / relative
    if not path.is_file():
      raise SchemaV2MigrationError(f"missing protected v1 artefact: {relative}")
    hashes[relative] = streaming_sha256(path)
  return hashes


def _assert_no_final_outputs_exist(root: Path) -> None:
  existing = [relative for relative in FINAL_RELATIVE_PATHS if (root / relative).exists()]
  if existing:
    raise SchemaV2MigrationError(
      f"refusing to overwrite existing schema v2 outputs: {existing}"
    )


def _atomic_publish(
  root: Path,
  staging_root: Path,
  relative_paths: tuple[str, ...],
  *,
  replace_fn: Any | None = None,
) -> None:
  """Publish staged outputs atomically with rollback on any failure.

  ``replace_fn`` defaults to ``os.replace`` and exists for controlled failure
  injection in tests.
  """
  replace = replace_fn or os.replace
  published: list[Path] = []
  try:
    for relative in relative_paths:
      staged = staging_root / relative
      if not staged.exists():
        raise SchemaV2MigrationError(f"missing staged output: {relative}")
      final = resolve_writable_path(root / relative)
      if final.exists():
        raise SchemaV2MigrationError(f"refusing to overwrite: {relative}")
      final.parent.mkdir(parents=True, exist_ok=True)
      published.append(final)
      replace(str(staged), str(final))
  except SchemaV2MigrationError:
    for final in published:
      if final.exists():
        final.unlink()
    raise
  except Exception as exc:
    for final in published:
      if final.exists():
        final.unlink()
    raise SchemaV2MigrationError(f"publication failed during atomic replace: {exc}") from exc


def migrate_schema_v2(
  root: Path | None = None,
  *,
  publish: bool,
  replace_fn: Any | None = None,
) -> dict[str, Any]:
  paths = ProjectPaths.from_repo_root(root)
  root = paths.root

  if publish:
    _assert_no_final_outputs_exist(root)

  protected_before = _hash_protected_inputs(root)
  accounting = MigrationAccounting()
  per_dataset_counts: dict[str, int] = {}

  staging_root = Path(tempfile.mkdtemp(prefix=".schema_v2_staging_", dir=str(root)))
  try:
    for dataset_id in ALL_DATASET_ORDER:
      v1_path = root / "data" / "interim" / dataset_id / f"{dataset_id}_canonical.jsonl"
      v2_path = staging_root / "data" / "interim" / "schema_v2" / dataset_id / f"{dataset_id}_canonical.jsonl"
      v2_path.parent.mkdir(parents=True, exist_ok=True)
      v1_records = read_canonical_jsonl(v1_path)
      v2_records = []
      for v1_record in v1_records:
        try:
          v2_records.append(migrate_v1_dict_to_v2(canonical_record_to_dict(v1_record), accounting))
        except MigrationError as exc:
          raise SchemaV2MigrationError(f"{dataset_id}: failed to migrate {v1_record.id}: {exc}") from exc
      write_canonical_jsonl_v2(v2_path, v2_records)
      per_dataset_counts[dataset_id] = len(v2_records)

    staged_inputs = [
      DatasetV2InputSpec(
        dataset_id=dataset_id,
        canonical_path=staging_root / "data" / "interim" / "schema_v2" / dataset_id / f"{dataset_id}_canonical.jsonl",
      )
      for dataset_id in ALL_DATASET_ORDER
    ]
    staged_pool_outputs = SchemaV2PoolOutputSpec(
      primary_path=staging_root / "data" / "processed" / "schema_v2" / "weak_pool" / "weak_pool_canonical.jsonl",
      auxiliary_path=staging_root / "data" / "processed" / "schema_v2" / "weak_pool" / "weak_pool_auxiliary.jsonl",
      membership_path=staging_root / "data" / "processed" / "schema_v2" / "weak_pool" / "weak_pool_membership.jsonl",
      manifest_path=staging_root / "outputs" / "manifests" / "schema_v2_weak_pool_manifest.json",
      summary_path=staging_root / "outputs" / "metrics" / "schema_v2_migration_summary.json",
    )
    pool_result = build_schema_v2_pools(staged_inputs, staged_pool_outputs)

    migration_manifest_path = staging_root / "outputs" / "manifests" / "schema_v2_migration_manifest.json"
    migration_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    migration_manifest = {
      "manifest_schema_version": MIGRATION_MANIFEST_SCHEMA_VERSION,
      "migration_version": MIGRATION_VERSION,
      "canonical_schema_version": SCHEMA_VERSION,
      "protected_v1_hashes_before": dict(sorted(protected_before.items())),
      "per_dataset_counts": dict(sorted(per_dataset_counts.items())),
      "accounting": accounting.to_dict(),
      "interim_outputs": {
        dataset_id: repo_relative_path(
          staging_root / "data" / "interim" / "schema_v2" / dataset_id / f"{dataset_id}_canonical.jsonl"
        )
        for dataset_id in ALL_DATASET_ORDER
      },
      "pool_outputs": pool_result["paths"],
    }
    migration_manifest_path.write_text(_deterministic_json(migration_manifest) + "\n", encoding="utf-8")

    actual = {
      **per_dataset_counts,
      "primary_pool": pool_result["primary_count"],
      "auxiliary_pool": pool_result["auxiliary_count"],
      "membership_rows": pool_result["membership_count"],
      "global_unique_ids": pool_result["global_unique_id_count"],
    }
    if actual != EXPECTED_COUNTS:
      raise SchemaV2MigrationError(f"count reconciliation failed: expected {EXPECTED_COUNTS}, got {actual}")

    protected_after = _hash_protected_inputs(root)
    if protected_after != protected_before:
      raise SchemaV2MigrationError("protected v1 hashes changed during migration")

    result: dict[str, Any] = {
      "published": False,
      "per_dataset_counts": per_dataset_counts,
      "pool_result": pool_result,
      "accounting": accounting.to_dict(),
      "protected_v1_hashes_before": protected_before,
      "protected_v1_hashes_after": protected_after,
      "expected_counts": EXPECTED_COUNTS,
      "actual_counts": actual,
    }

    if publish:
      _atomic_publish(root, staging_root, FINAL_RELATIVE_PATHS, replace_fn=replace_fn)
      result["published"] = True
      result["output_paths"] = list(FINAL_RELATIVE_PATHS)

    return result
  finally:
    if staging_root.exists():
      shutil.rmtree(staging_root, ignore_errors=True)
