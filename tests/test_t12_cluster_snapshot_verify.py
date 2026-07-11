"""CPU tests for T12 cluster snapshot verification."""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

from ambiguity_manager.model.cluster.snapshot_verify import (
    CANONICAL_RESOLVED_BYTES,
    CANONICAL_RESOLVED_FILES,
    CANONICAL_REVISION,
    CANONICAL_SAFETENSORS_SHARDS,
    SnapshotExpectations,
    verify_snapshot,
)
from tests.t12_cluster_test_helpers import build_synthetic_snapshot_tree, snapshot_expectations_from_tree


class T12ClusterSnapshotVerifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.base = Path(self._tmpdir.name)

    def test_valid_synthetic_snapshot_tree_passes(self) -> None:
        snapshot_root = build_synthetic_snapshot_tree(self.base)
        expectations = snapshot_expectations_from_tree(snapshot_root)
        result = verify_snapshot(snapshot_root, expectations=expectations)
        self.assertEqual(result.status, "pass", msg=result.rejection_reasons)

    def test_canonical_inventory_mismatch_fails(self) -> None:
        snapshot_root = build_synthetic_snapshot_tree(self.base)
        result = verify_snapshot(snapshot_root)
        self.assertEqual(result.status, "fail")
        self.assertIn("resolved_total_bytes_mismatch", result.rejection_reasons)

    def test_wrong_revision_directory_fails(self) -> None:
        snapshot_root = build_synthetic_snapshot_tree(self.base, revision="badrevision")
        result = verify_snapshot(snapshot_root)
        self.assertIn("revision_directory_mismatch", result.rejection_reasons)

    @unittest.skipIf(os.name == "nt", "broken symlink creation requires elevated privileges on Windows")
    def test_broken_symlink_fails(self) -> None:
        snapshot_root = build_synthetic_snapshot_tree(self.base, include_broken_symlink=True)
        result = verify_snapshot(
            snapshot_root,
            expectations=SnapshotExpectations(
                resolved_files=CANONICAL_RESOLVED_FILES + 1,
                resolved_bytes=0,
                safetensors_shards=CANONICAL_SAFETENSORS_SHARDS,
            ),
        )
        self.assertIn("broken_symlinks_present", result.rejection_reasons)

    def test_missing_required_file_fails(self) -> None:
        snapshot_root = build_synthetic_snapshot_tree(self.base)
        (snapshot_root / "config.json").unlink()
        result = verify_snapshot(snapshot_root)
        self.assertIn("missing_required_file:config.json", result.rejection_reasons)

    def test_wrong_shard_count_fails(self) -> None:
        snapshot_root = build_synthetic_snapshot_tree(self.base, safetensors_shards=3)
        result = verify_snapshot(snapshot_root)
        self.assertIn("safetensors_shard_count_mismatch", result.rejection_reasons)

    def test_no_refs_directory_is_acceptable(self) -> None:
        snapshot_root = build_synthetic_snapshot_tree(self.base)
        expectations = snapshot_expectations_from_tree(snapshot_root)
        refs = snapshot_root.parent.parent / "refs"
        self.assertFalse(refs.exists())
        result = verify_snapshot(snapshot_root, expectations=expectations)
        self.assertEqual(result.status, "pass")

    def test_hub_cache_relationship(self) -> None:
        snapshot_root = build_synthetic_snapshot_tree(self.base, hub_layout=True)
        result = verify_snapshot(
            snapshot_root,
            expectations=SnapshotExpectations(
                resolved_files=12,
                resolved_bytes=768,
                safetensors_shards=CANONICAL_SAFETENSORS_SHARDS,
            ),
        )
        self.assertTrue(result.hub_cache_relationship_valid)
        self.assertTrue(result.snapshot_path.endswith(CANONICAL_REVISION))


if __name__ == "__main__":
    unittest.main()
