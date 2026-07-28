import json
import tempfile
import unittest
from pathlib import Path

from ambiguity_manager.model.t28_trainer import (
    T28TrainerError,
    T28RunOrchestrator,
    build_emitted_target_manifest_entry,
    validate_full_data_contract,
    verify_package_checksums,
)


class T28R4ContractTests(unittest.TestCase):
    def test_full_data_contract_rejects_smoke_subset_and_protected_roles(self):
        with self.assertRaises(T28TrainerError):
            validate_full_data_contract({"record_count": 192, "target_count": 192})
        with self.assertRaises(T28TrainerError):
            validate_full_data_contract({"record_count": 11294, "target_count": 13058, "source_holdout_loaded": 1})

    def test_full_data_contract_requires_all_identity_hashes(self):
        with self.assertRaises(T28TrainerError):
            validate_full_data_contract({"record_count": 11294, "target_count": 13058})

    def test_emitted_target_manifest_contains_required_provenance(self):
        entry = build_emitted_target_manifest_entry(
            {"id": "r1", "group_key": "g1", "source_dataset": "vague", "split": "source_train"},
            task="predict_intent_v1", prompt="p", target="t", included=True,
        )
        self.assertEqual(entry["record_id"], "r1")
        self.assertIn("prompt_hash", entry)
        self.assertIn("target_hash", entry)
        self.assertEqual(entry["eligibility_reason"], "included")

    def test_orchestrator_is_sequential_and_matrix_immutable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            matrix = root / "matrix.json"
            matrix.write_text(json.dumps({"frozen": True, "runs": [{"run_id": "r1"}]}))
            out = root / "out"
            orch = T28RunOrchestrator(matrix, out)
            self.assertEqual(orch.run_ids(), ["r1"])
            with self.assertRaises(T28TrainerError):
                matrix.write_text(json.dumps({"frozen": True, "runs": [{"run_id": "r2"}]}))
                orch.verify_immutable()

    def test_package_checksums_are_verified(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "weights.safetensors").write_bytes(b"x")
            manifest = {"files": {"weights.safetensors": "2d711642b726b04401627ca9fbac32f5da7e6e5c2c7b8c3c3b2a1a2b3c4d5e6f"}}
            self.assertFalse(verify_package_checksums(root, manifest))


if __name__ == "__main__":
    unittest.main()
