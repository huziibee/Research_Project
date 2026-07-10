"""Tests for schema v2 pool rebuild and migration orchestration."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ambiguity_manager.data_audit.readers import streaming_sha256
from ambiguity_manager.migration.pool_builder import (
  DATASET_ROLE_CONFIG,
  DatasetV2InputSpec,
  SchemaV2PoolBuildError,
  SchemaV2PoolOutputSpec,
  build_schema_v2_pools,
)
from ambiguity_manager.migration.run_migration import (
  FINAL_RELATIVE_PATHS,
  SchemaV2MigrationError,
  migrate_schema_v2,
)
from ambiguity_manager.migration.v1_to_v2 import migrate_v1_dict_to_v2
from ambiguity_manager.paths import repo_relative_path
from ambiguity_manager.schema.jsonl import write_canonical_jsonl
from ambiguity_manager.schema.records import canonical_record_from_dict
from ambiguity_manager.schema.v2.jsonl import write_canonical_jsonl_v2

FIXTURES = Path(__file__).parent / "fixtures" / "migration"
WEAK_FIXTURES = Path(__file__).parent / "fixtures" / "weak_pool"


class MigrationV2PoolTests(unittest.TestCase):
  def setUp(self) -> None:
    self._tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self._tmp.cleanup)
    self.root = Path(self._tmp.name).resolve()
    (self.root / "pyproject.toml").write_text("[project]\nname='tmp'\n", encoding="utf-8")
    patcher = mock.patch("ambiguity_manager.paths.repo_root", return_value=self.root.resolve())
    patcher.start()
    self.addCleanup(patcher.stop)

  def _write_v1_and_migrate(self, dataset_id: str, fixture_name: str) -> Path:
    v1_path = self.root / "data" / "interim" / dataset_id / f"{dataset_id}_canonical.jsonl"
    v1_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(WEAK_FIXTURES / fixture_name, v1_path)
    v2_path = self.root / "data" / "interim" / "schema_v2" / dataset_id / f"{dataset_id}_canonical.jsonl"
    v2_path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for line in v1_path.read_text(encoding="utf-8").splitlines():
      if not line.strip():
        continue
      payload = json.loads(line)
      records.append(migrate_v1_dict_to_v2(payload))
    write_canonical_jsonl_v2(v2_path, records)
    return v2_path

  def _install_v1_pools(self) -> None:
    pool_dir = self.root / "data" / "processed" / "weak_pool"
    pool_dir.mkdir(parents=True, exist_ok=True)
    for name in ("weak_pool_canonical.jsonl", "weak_pool_auxiliary.jsonl", "weak_pool_membership.jsonl"):
      (pool_dir / name).write_text("{}\n", encoding="utf-8")

  def test_clariq_auxiliary_separation(self) -> None:
    for dataset_id, fixture in [
      ("ambik", "tiny_ambik.jsonl"),
      ("indirect_requests", "tiny_indirect_requests.jsonl"),
      ("codraw_icr_v2", "tiny_codraw_icr_v2.jsonl"),
      ("vague", "tiny_vague.jsonl"),
      ("clara", "tiny_clara.jsonl"),
      ("clariq", "tiny_clariq.jsonl"),
    ]:
      self._write_v1_and_migrate(dataset_id, fixture)
    inputs = [
      DatasetV2InputSpec(
        dataset_id=dataset_id,
        canonical_path=self.root / "data" / "interim" / "schema_v2" / dataset_id / f"{dataset_id}_canonical.jsonl",
      )
      for dataset_id in DATASET_ROLE_CONFIG
    ]
    outputs = SchemaV2PoolOutputSpec(
      primary_path=self.root / "data" / "processed" / "schema_v2" / "weak_pool" / "weak_pool_canonical.jsonl",
      auxiliary_path=self.root / "data" / "processed" / "schema_v2" / "weak_pool" / "weak_pool_auxiliary.jsonl",
      membership_path=self.root / "data" / "processed" / "schema_v2" / "weak_pool" / "weak_pool_membership.jsonl",
      manifest_path=self.root / "outputs" / "manifests" / "schema_v2_weak_pool_manifest.json",
      summary_path=self.root / "outputs" / "metrics" / "schema_v2_migration_summary.json",
    )
    result = build_schema_v2_pools(inputs, outputs)
    self.assertGreater(result["auxiliary_count"], 0)
    self.assertGreater(result["primary_count"], 0)
    auxiliary_text = outputs.auxiliary_path.read_text(encoding="utf-8")
    self.assertIn('"source_dataset": "clariq"', auxiliary_text)
    self.assertNotIn("safe_agent_bench", auxiliary_text)

  def test_no_overwrite(self) -> None:
    target = self.root / FINAL_RELATIVE_PATHS[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("existing\n", encoding="utf-8")
    with self.assertRaises(SchemaV2MigrationError):
      migrate_schema_v2(self.root, publish=True)

  def test_validate_only_does_not_publish(self) -> None:
    if not Path("data/interim/ambik/ambik_canonical.jsonl").exists():
      self.skipTest("production v1 artefacts unavailable in temp root")
    with self.assertRaises(SchemaV2MigrationError):
      migrate_schema_v2(self.root, publish=False)


if __name__ == "__main__":
  unittest.main()
