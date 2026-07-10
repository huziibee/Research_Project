"""Publication failure injection tests for schema v2 migration."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ambiguity_manager.data_audit.readers import streaming_sha256
from ambiguity_manager.migration.run_migration import (
  FINAL_RELATIVE_PATHS,
  SchemaV2MigrationError,
  _atomic_publish,
  migrate_schema_v2,
)
from ambiguity_manager.migration.v1_to_v2 import migrate_v1_dict_to_v2
from ambiguity_manager.schema.v2.jsonl import write_canonical_jsonl_v2

WEAK_FIXTURES = Path(__file__).parent / "fixtures" / "weak_pool"

TINY_EXPECTED_COUNTS = {
  "ambik": 1,
  "indirect_requests": 1,
  "codraw_icr_v2": 1,
  "vague": 1,
  "clara": 1,
  "clariq": 1,
  "primary_pool": 5,
  "auxiliary_pool": 1,
  "membership_rows": 6,
  "global_unique_ids": 6,
}


class PublicationFailureTests(unittest.TestCase):
  def setUp(self) -> None:
    self._tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self._tmp.cleanup)
    self.root = Path(self._tmp.name).resolve()
    (self.root / "pyproject.toml").write_text("[project]\nname='tmp'\n", encoding="utf-8")
    patcher = mock.patch("ambiguity_manager.paths.repo_root", return_value=self.root.resolve())
    patcher.start()
    self.addCleanup(patcher.stop)

  def _install_tiny_v1_artefacts(self) -> dict[str, str]:
    v1_hashes: dict[str, str] = {}
    for dataset_id, fixture in [
      ("ambik", "tiny_ambik.jsonl"),
      ("indirect_requests", "tiny_indirect_requests.jsonl"),
      ("codraw_icr_v2", "tiny_codraw_icr_v2.jsonl"),
      ("vague", "tiny_vague.jsonl"),
      ("clara", "tiny_clara.jsonl"),
      ("clariq", "tiny_clariq.jsonl"),
    ]:
      path = self.root / "data" / "interim" / dataset_id / f"{dataset_id}_canonical.jsonl"
      path.parent.mkdir(parents=True, exist_ok=True)
      shutil.copyfile(WEAK_FIXTURES / fixture, path)
      v1_hashes[str(path.relative_to(self.root)).replace("\\", "/")] = streaming_sha256(path)
    pool_dir = self.root / "data" / "processed" / "weak_pool"
    pool_dir.mkdir(parents=True, exist_ok=True)
    for name, content in (
      ("weak_pool_canonical.jsonl", '{"id":"x"}\n'),
      ("weak_pool_auxiliary.jsonl", '{"id":"y"}\n'),
      ("weak_pool_membership.jsonl", '{"id":"x"}\n'),
    ):
      path = pool_dir / name
      path.write_text(content, encoding="utf-8")
      v1_hashes[str(path.relative_to(self.root)).replace("\\", "/")] = streaming_sha256(path)
    return v1_hashes

  def test_atomic_publish_rolls_back_after_partial_replace(self) -> None:
    staging = self.root / ".staging"
    staging.mkdir()
    for relative in FINAL_RELATIVE_PATHS:
      path = staging / relative
      path.parent.mkdir(parents=True, exist_ok=True)
      path.write_text(json.dumps({"path": relative}) + "\n", encoding="utf-8")

    preexisting = self.root / "data" / "interim" / "protected_marker.txt"
    preexisting.parent.mkdir(parents=True, exist_ok=True)
    preexisting.write_bytes(b"unchanged-marker")
    pre_hash = streaming_sha256(preexisting)

    calls: list[str] = []

    def failing_replace(src: str, dst: str) -> None:
      calls.append(dst)
      os.replace(src, dst)
      if len(calls) >= 2:
        raise OSError("injected publication failure")

    with self.assertRaises(SchemaV2MigrationError):
      _atomic_publish(self.root, staging, FINAL_RELATIVE_PATHS, replace_fn=failing_replace)

    self.assertGreaterEqual(len(calls), 2, "failure must occur after at least one successful replace")
    for relative in FINAL_RELATIVE_PATHS:
      final = self.root / relative
      self.assertFalse(final.exists(), f"partial output must be absent: {relative}")
    self.assertEqual(streaming_sha256(preexisting), pre_hash)
    unpublished = FINAL_RELATIVE_PATHS[len(calls) :]
    for relative in unpublished:
      self.assertTrue((staging / relative).exists(), f"unpublished staging file should remain: {relative}")

  def test_migrate_publish_rolls_back_on_injected_failure(self) -> None:
    v1_before = self._install_tiny_v1_artefacts()
    staging_dirs_before = list(self.root.glob(".schema_v2_staging_*"))

    calls: list[str] = []

    def failing_replace(src: str, dst: str) -> None:
      calls.append(dst)
      os.replace(src, dst)
      if len(calls) >= 2:
        raise OSError("injected publication failure")

    with mock.patch("ambiguity_manager.migration.run_migration.EXPECTED_COUNTS", TINY_EXPECTED_COUNTS):
      with self.assertRaises(SchemaV2MigrationError) as ctx:
        migrate_schema_v2(self.root, publish=True, replace_fn=failing_replace)

    self.assertIn("publication failed", str(ctx.exception).lower())
    self.assertGreaterEqual(len(calls), 2)
    for relative in FINAL_RELATIVE_PATHS:
      self.assertFalse((self.root / relative).exists(), f"no partial publish: {relative}")
    staging_dirs_after = list(self.root.glob(".schema_v2_staging_*"))
    self.assertEqual(staging_dirs_after, staging_dirs_before, "staging temp dirs must be removed")
    v1_after_hashes = {
      path: streaming_sha256(self.root / path) for path in v1_before
    }
    self.assertEqual(v1_after_hashes, v1_before)

  def test_migrate_publish_success_leaves_no_staging(self) -> None:
    self._install_tiny_v1_artefacts()
    with mock.patch("ambiguity_manager.migration.run_migration.EXPECTED_COUNTS", TINY_EXPECTED_COUNTS):
      result = migrate_schema_v2(self.root, publish=True)
    self.assertTrue(result["published"])
    self.assertFalse(list(self.root.glob(".schema_v2_staging_*")))


if __name__ == "__main__":
  unittest.main()
