"""Tests for the frozen model-selection development bake-off set."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.data.model_selection_set import (  # noqa: E402
    DATASET_DIR,
    EXPERIMENT_CONFIG,
    SET_ID,
    dataset_paths,
    load_model_selection_development_set,
    manifest_hash,
    validate_model_selection_manifest,
)
from ambiguity_manager.paths import ProjectPaths  # noqa: E402

PROJECT_ROOT = ProjectPaths.from_repo_root().root
PATHS = dataset_paths(PROJECT_ROOT)
EXPERIMENT_PATH = PROJECT_ROOT / EXPERIMENT_CONFIG


class ModelSelectionDevelopmentSetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_model_selection_development_set(PROJECT_ROOT)
        cls.manifest = cls.dataset.manifest
        cls.experiment = json.loads(EXPERIMENT_PATH.read_text(encoding="utf-8"))

    def test_record_count_target(self) -> None:
        self.assertEqual(self.manifest["record_count"], 40)
        self.assertEqual(len(self.dataset.inputs), 40)
        self.assertGreaterEqual(self.manifest["record_count"], 32)
        self.assertLessEqual(self.manifest["record_count"], 48)

    def test_development_only_flags(self) -> None:
        self.assertTrue(self.manifest["development_only"])
        self.assertFalse(self.manifest["protected"])
        self.assertFalse(self.manifest["valid_for_official_final_claims"])
        self.assertTrue(self.experiment["development_only"])
        self.assertFalse(self.experiment["protected"])
        self.assertFalse(self.experiment["valid_for_official_final_claims"])

    def test_sources_breakdown(self) -> None:
        self.assertEqual(
            self.manifest["sources"],
            {
                "t16_t24_synthetic": 16,
                "t12_schema_v2_synthetic": 10,
                "hand_authored_msel_dev": 14,
            },
        )

    def test_no_calibration_or_future_manual_ids(self) -> None:
        quality = json.loads(PATHS["quality_controls"].read_text(encoding="utf-8"))
        self.assertEqual(quality["calibration_id_overlap"], [])
        self.assertEqual(quality["future_manual_id_overlap"], [])
        self.assertTrue(quality["calibration_exclusion_passed"])
        self.assertTrue(quality["namespace_separation_passed"])

    def test_all_records_excluded_from_future_manual_challenge_set(self) -> None:
        for entry in self.manifest["records"]:
            self.assertTrue(entry["excluded_from_future_manual_challenge_set"])

    def test_transport_smoke_subset(self) -> None:
        self.assertEqual(
            self.dataset.transport_smoke_ids,
            [
                "msel_t12_syn_001",
                "msel_t12_syn_002",
                "msel_t12_syn_003",
                "msel_t12_syn_005",
            ],
        )
        for rid in self.dataset.transport_smoke_ids:
            self.assertIn(rid, self.dataset.record_ids)

    def test_manifest_hash_stable(self) -> None:
        recomputed = manifest_hash(self.manifest)
        self.assertEqual(self.manifest["manifest_hash"], recomputed)
        self.assertEqual(self.experiment["dataset_manifest_hash"], recomputed)

    def test_manifest_file_hashes_match(self) -> None:
        from ambiguity_manager.data.model_selection_set import sha256_file

        hashes = self.manifest["hashes"]
        self.assertEqual(hashes["inputs_sha256"], sha256_file(PATHS["inputs"]))
        self.assertEqual(hashes["gold_sha256"], sha256_file(PATHS["gold"]))

    def test_no_protected_data(self) -> None:
        quality = json.loads(PATHS["quality_controls"].read_text(encoding="utf-8"))
        self.assertEqual(quality["protected_data_records"], [])

    def test_unsupported_label_audit_passed(self) -> None:
        quality = json.loads(PATHS["quality_controls"].read_text(encoding="utf-8"))
        self.assertTrue(quality["unsupported_label_audit"]["unsupported_label_audit_passed"])

    def test_t12_records_are_route_pressure_only(self) -> None:
        t12_ids = [f"msel_t12_syn_{index:03d}" for index in range(1, 11)]
        by_id = {entry["record_id"]: entry for entry in self.manifest["records"]}
        for rid in t12_ids:
            entry = by_id[rid]
            self.assertEqual(entry["available_gold_weak_fields"], [])
            self.assertTrue(entry["metric_eligibility"]["routing"])
            self.assertFalse(entry["metric_eligibility"]["intent_slots"])

    def test_context_pair_present(self) -> None:
        grouping = {entry["grouping_key"] for entry in self.manifest["records"]}
        self.assertIn("context_benefit_pair:package_shelf", grouping)
        ids = {
            entry["record_id"]
            for entry in self.manifest["records"]
            if entry["grouping_key"] == "context_benefit_pair:package_shelf"
        }
        self.assertEqual(ids, {"msel_dev_context_rich", "msel_dev_context_minimal"})

    def test_no_manual_2026_namespace_ids(self) -> None:
        for rid in self.dataset.record_ids:
            self.assertFalse(rid.startswith("manual:2026:"))

    def test_validate_manifest_accepts_current_bundle(self) -> None:
        errors = validate_model_selection_manifest(
            self.manifest,
            inputs=self.dataset.inputs,
            gold=self.dataset.gold,
            transport_smoke_ids=self.dataset.transport_smoke_ids,
        )
        self.assertEqual(errors, [])

    def test_manifest_id(self) -> None:
        self.assertEqual(self.manifest["manifest_id"], SET_ID)
        self.assertEqual(self.experiment["config_id"], SET_ID)
        self.assertTrue(str(self.experiment["dataset_manifest_path"]).endswith(f"{DATASET_DIR}/manifest.json"))


if __name__ == "__main__":
    unittest.main()
