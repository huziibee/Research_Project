"""T28-R2 licence, dependency, provenance, and permission-gate tests."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from ambiguity_manager.governance.dataset_licence import validate_dataset_licence_register
from ambiguity_manager.model.t28 import T28Error, assert_dataset_training_permissions


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "dataset_licence_status",
    "dataset_licence_identifier",
    "code_licence_identifier",
    "evidence_type",
    "evidence_url_or_path",
    "evidence_hash",
    "exact_upstream_revision",
    "training_permission",
    "development_evaluation_permission",
    "redistribution_permission",
    "derived_label_permission",
    "model_weight_release_permission",
    "dependency_status",
    "unresolved_reason",
}


class T28R2GovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = ROOT / "configs/licences/dataset_licence_register.json"
        cls.data = json.loads(cls.path.read_text(encoding="utf-8"))

    def test_all_six_sources_have_explicit_governance_fields(self) -> None:
        entries = {entry["dataset_id"]: entry for entry in self.data["entries"]}
        for dataset_id in ("ambik", "indirect_requests", "codraw_icr_v2", "vague", "clara", "clariq"):
            self.assertIn(dataset_id, entries)
            self.assertTrue(REQUIRED <= entries[dataset_id].keys(), dataset_id)

    def test_dataset_and_code_licences_are_separate(self) -> None:
        entry = next(item for item in self.data["entries"] if item["dataset_id"] == "codraw_icr_v2")
        self.assertIn("dataset_licence_identifier", entry)
        self.assertIn("code_licence_identifier", entry)
        self.assertNotEqual("code_licence_identifier", "dataset_licence_identifier")

    def test_unresolved_sources_block_t28_training(self) -> None:
        entries = {entry["dataset_id"]: entry for entry in self.data["entries"]}
        for dataset_id in ("ambik", "indirect_requests", "codraw_icr_v2", "vague", "clara"):
            self.assertEqual(entries[dataset_id]["verification_status"], "unresolved")
            self.assertNotEqual(entries[dataset_id]["training_permission"], "permitted")

    def test_public_availability_cannot_verify(self) -> None:
        bad = copy.deepcopy(self.data)
        entry = next(item for item in bad["entries"] if item["dataset_id"] == "ambik")
        entry["verification_status"] = "verified"
        entry["evidence_type"] = "public_repository_only"
        entry["evidence_url_or_path"] = "https://github.com/cog-model/AmbiK-dataset"
        entry["evidence_hash"] = "a" * 64
        self.assertTrue(validate_dataset_licence_register(bad))

    def test_missing_evidence_hash_rejected_for_verified_entry(self) -> None:
        bad = copy.deepcopy(self.data)
        entry = bad["entries"][0]
        entry["verification_status"] = "verified"
        entry["evidence_type"] = "official_dataset_card"
        entry["evidence_url_or_path"] = "https://example.invalid/card"
        entry["evidence_hash"] = None
        entry["training_permission"] = "permitted"
        self.assertTrue(any("evidence_hash" in error for error in validate_dataset_licence_register(bad)))

    def test_unresolved_dependency_is_a_gate(self) -> None:
        bad = copy.deepcopy(self.data)
        entry = next(item for item in bad["entries"] if item["dataset_id"] == "ambik")
        entry["verification_status"] = "verified"
        entry["dependency_status"] = "unresolved"
        self.assertTrue(any("dependency" in error for error in validate_dataset_licence_register(bad)))

    def test_rights_matrix_has_twelve_noncollapsed_rights(self) -> None:
        matrix = json.loads((ROOT / "docs/licences/T28_dataset_rights_matrix.json").read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["rights"]), 12)
        self.assertEqual(len(matrix["sources"]), 6)

    def test_r1_hashes_and_t15_manifest_are_pinned(self) -> None:
        manifest = json.loads((ROOT / "data/processed/weak_pool/weak_pool_canonical.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["canonical_sha256"], "1e51cac046e014a6b890b10a155d22e32e01aa276d4507a10ad4f86abcf9942a")
        self.assertEqual(manifest["permitted_view_sha256"], "34b551c37c8f97c24c1263a2cc12a9497e65f754924f1404c47055999f04ea22")

    def test_training_entry_gate_rejects_unresolved_permissions(self) -> None:
        with self.assertRaisesRegex(T28Error, "dataset_permission_gate_blocked"):
            assert_dataset_training_permissions(self.path, ["ambik", "clara"])


if __name__ == "__main__":
    unittest.main()
