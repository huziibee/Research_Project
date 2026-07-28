import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ambiguity_manager.model.t28 import (
    T28Error,
    assert_dev_only,
    assert_group_disjoint,
    assert_train_only,
    choose_checkpoint,
    freeze_plan,
    package_manifest,
    require_same_adapter,
)


class T28ContractTests(unittest.TestCase):
    def test_train_only_enforcement_rejects_dev_and_protected(self):
        with self.assertRaises(T28Error):
            assert_train_only([{"split": "source_dev", "protected_data": False}])
        with self.assertRaises(T28Error):
            assert_train_only([{"split": "source_train", "protected_data": True}])

    def test_dev_only_evaluation_rejects_train(self):
        with self.assertRaises(T28Error):
            assert_dev_only([{"split": "source_train", "protected_data": False}])

    def test_group_disjoint_validation(self):
        assert_group_disjoint([{"group_id": "a"}], [{"group_id": "b"}])
        with self.assertRaises(T28Error):
            assert_group_disjoint([{"group_id": "a"}], [{"group_id": "a"}])

    def test_frozen_plan_is_immutable(self):
        plan = {"plan_id": "t28-v1", "source_commit": "a" * 40}
        with tempfile.TemporaryDirectory() as td:
            path = freeze_plan(Path(td) / "plan.json", plan)
            with self.assertRaises(T28Error):
                freeze_plan(path, {**plan, "source_commit": "b" * 40})

    def test_checkpoint_ranking_and_safety_disqualification(self):
        candidates = [
            {"checkpoint": "step-2", "eligible": True, "primary": 0.8, "schema_validity": 1.0},
            {"checkpoint": "step-1", "eligible": True, "primary": 0.8, "schema_validity": 1.0},
            {"checkpoint": "step-3", "eligible": False, "primary": 1.0, "schema_validity": 1.0},
        ]
        self.assertEqual(choose_checkpoint(candidates)["checkpoint"], "step-1")

    def test_same_adapter_and_no_adapter_rejection(self):
        require_same_adapter("adapter-sha256:x", "adapter-sha256:x")
        with self.assertRaises(T28Error):
            require_same_adapter("adapter-sha256:x", "no_adapter")
        with self.assertRaises(T28Error):
            require_same_adapter("adapter-sha256:x", "adapter-sha256:y")

    def test_package_manifest_contains_checksums(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "adapter.bin").write_bytes(b"adapter")
            manifest = package_manifest(root, {"base_revision": "b" * 40})
            expected = hashlib.sha256(b"adapter").hexdigest()
            self.assertEqual(manifest["files"]["adapter.bin"], expected)


if __name__ == "__main__":
    unittest.main()
