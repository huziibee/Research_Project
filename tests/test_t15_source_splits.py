"""CPU-only tests for the T15 source-development data split programme.

Validates the artefacts produced by ``scripts/build_source_data_splits.py``
under ``data/development/source_splits_v1/`` against the requirements in
``configs/data/source_split_policy_v1.json``.

Run with::

    python -m unittest tests.test_t15_source_splits -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.data import source_splits as ss  # noqa: E402
from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex  # noqa: E402


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            rows.append(json.loads(stripped))
    return rows


class SourceSplitProgrammeTests(unittest.TestCase):
    """Validates the persisted real programme artefacts."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.paths = ss.dataset_paths(ROOT)
        for name, path in cls.paths.items():
            if name == "dataset_dir":
                continue
            if not path.is_file():
                raise AssertionError(
                    f"missing built artefact {path}; run "
                    "'python scripts/build_source_data_splits.py' first"
                )
        cls.manifest = json.loads(cls.paths["manifest"].read_text(encoding="utf-8"))
        cls.coverage = json.loads(cls.paths["coverage_report"].read_text(encoding="utf-8"))
        cls.leakage = json.loads(cls.paths["leakage_report"].read_text(encoding="utf-8"))
        cls.eligibility = json.loads(cls.paths["eligibility_summary"].read_text(encoding="utf-8"))
        cls.hashes = json.loads(cls.paths["hashes"].read_text(encoding="utf-8"))
        cls.record_rows = _read_jsonl(cls.paths["record_manifest"])
        cls.group_rows = _read_jsonl(cls.paths["group_manifest"])
        cls.policy = ss.load_policy(ROOT)

    # 1. seed recorded
    def test_seed_recorded(self) -> None:
        self.assertEqual(self.policy["seed"], 20260722)
        self.assertEqual(self.manifest["policy_seed"], 20260722)

    # 2. coverage reconciles
    def test_coverage_reconciles(self) -> None:
        reconciliation = self.coverage["reconciliation"]
        self.assertTrue(reconciliation["reconciled"])
        self.assertEqual(reconciliation["total_input_records"], reconciliation["total_output_records"])
        self.assertEqual(reconciliation["total_output_records"], len(self.record_rows))
        self.assertEqual(reconciliation["total_output_records"], self.manifest["record_counts"]["total_output"])

    # 3. percentages within documented tolerance
    def test_percentages_within_tolerance(self) -> None:
        self.assertTrue(self.coverage["primary"]["within_tolerance"])
        self.assertTrue(self.coverage["auxiliary"]["within_tolerance"])
        tolerance = self.coverage["tolerance_max_absolute_percentage_point_deviation"]
        for value in self.coverage["primary"]["deviation_percentage_points"].values():
            self.assertLessEqual(abs(value), tolerance)
        for value in self.coverage["auxiliary"]["deviation_percentage_points"].values():
            self.assertLessEqual(abs(value), tolerance)

    # 4. no group crosses a split boundary
    def test_no_cross_split_groups(self) -> None:
        self.assertGreater(len(self.group_rows), 0)
        for row in self.group_rows:
            self.assertEqual(row["split_count"], 1, msg=row)
            self.assertIsNotNone(row["split"])

    # 5. group manifest fully accounts for every record
    def test_group_manifest_accounts_for_every_record(self) -> None:
        total_members = sum(row["member_count"] for row in self.group_rows)
        self.assertEqual(total_members, len(self.record_rows))
        record_group_keys = {row["group_key"] for row in self.record_rows}
        group_manifest_keys = {row["group_key"] for row in self.group_rows}
        self.assertEqual(record_group_keys, group_manifest_keys)

    # 6. ClariQ is auxiliary only
    def test_clariq_auxiliary_only(self) -> None:
        seen_clariq = False
        for row in self.record_rows:
            if row["source_dataset"] == "clariq":
                seen_clariq = True
                self.assertIn(row["split"], {"auxiliary_train", "auxiliary_dev"})
            else:
                self.assertIn(row["split"], {"source_train", "source_dev", "source_holdout"})
        self.assertTrue(seen_clariq)

    # 7. TEACh excluded
    def test_teach_excluded(self) -> None:
        allowed = ss.PRIMARY_ALLOWED_DATASETS | ss.AUXILIARY_ALLOWED_DATASETS
        for row in self.record_rows:
            self.assertIn(row["source_dataset"], allowed)
            self.assertNotIn(row["source_dataset"], ss.FORBIDDEN_DATASETS)
        self.assertEqual(self.leakage["checks"]["teach_source_dataset_records"], [])
        self.assertTrue(self.leakage["passed"]["teach_source_dataset_records"])

    # 8. no T13 calibration leakage (ids or commands)
    def test_no_t13_calibration_leakage(self) -> None:
        self.assertEqual(self.leakage["checks"]["t13_calibration_id_overlap"], [])
        self.assertEqual(self.leakage["checks"]["t13_calibration_command_overlap"], [])
        self.assertEqual(self.leakage["reference_counts"]["calibration_ids"], 24)

    # 9. no future manual namespace leakage
    def test_no_future_manual_namespace_leakage(self) -> None:
        self.assertEqual(self.leakage["checks"]["future_manual_namespace_id_overlap"], [])
        self.assertTrue(self.leakage["passed"]["future_manual_namespace_id_overlap"])

    # 10. no 40-record model-selection set leakage
    def test_no_model_selection_leakage(self) -> None:
        self.assertEqual(self.leakage["checks"]["model_selection_id_overlap"], [])
        self.assertEqual(self.leakage["checks"]["model_selection_command_overlap"], [])
        self.assertEqual(self.leakage["reference_counts"]["model_selection_ids"], 40)

    # 11. no synthetic evaluator fixture leakage
    def test_no_synthetic_fixture_leakage(self) -> None:
        self.assertEqual(self.leakage["checks"]["synthetic_evaluator_fixture_command_overlap"], [])
        self.assertGreater(self.leakage["reference_counts"]["synthetic_fixture_commands"], 0)

    # 12. missing labels are never converted to a negative value
    def test_missing_not_converted_to_negative(self) -> None:
        by_task = self.eligibility["by_task"]
        self.assertGreater(by_task["cpc"]["unavailable"], 0)
        self.assertGreater(by_task["candidate_interpretations"]["unavailable"], 0)
        self.assertGreater(by_task["uncertainty_sampling"]["unavailable"], 0)
        for task_counts in by_task.values():
            self.assertEqual(set(task_counts), set(ss.ELIGIBILITY_VALUES))

    # 13. weak signals are marked weakly_eligible, not eligible
    def test_weak_marked_weak(self) -> None:
        by_task = self.eligibility["by_task"]
        self.assertGreater(by_task["clarification_target"]["weakly_eligible"], 0)
        self.assertGreater(by_task["structured_training_target"]["weakly_eligible"], 0)
        self.assertGreater(by_task["compound_ambiguity"]["weakly_eligible"], 0)

    # 14. eligibility values are restricted to the documented enum
    def test_eligibility_values_are_enum(self) -> None:
        allowed = set(ss.ELIGIBILITY_VALUES)
        self.assertEqual(len(allowed), 4)
        for row in self.record_rows:
            self.assertEqual(set(row["eligibility"]), set(ss.TASK_NAMES))
            for status in row["eligibility"].values():
                self.assertIn(status, allowed)

    # 15. source_holdout is explicitly not the final protected manual benchmark
    def test_source_holdout_not_final_protected_benchmark(self) -> None:
        self.assertTrue(self.manifest["source_holdout_is_not_manual_protected_challenge_set"])
        self.assertFalse(self.manifest["protected"])
        self.assertFalse(self.manifest["valid_for_official_final_claims"])
        joined_notes = " ".join(self.manifest["notes"])
        self.assertIn("not the final protected manual benchmark", joined_notes)
        policy_note = self.policy["protected_status"]["note"]
        self.assertIn("manual_protected_challenge_set", policy_note)
        self.assertIn("NOT", policy_note)

    # 16. canonical hashes are internally consistent and deterministic
    def test_hashes_deterministic(self) -> None:
        self.assertEqual(self.hashes["record_manifest_sha256"], ss.sha256_file(self.paths["record_manifest"]))
        self.assertEqual(self.hashes["group_manifest_sha256"], ss.sha256_file(self.paths["group_manifest"]))
        self.assertEqual(self.hashes["coverage_report_sha256"], ss.sha256_file(self.paths["coverage_report"]))
        self.assertEqual(
            self.hashes["eligibility_summary_sha256"], ss.sha256_file(self.paths["eligibility_summary"])
        )
        self.assertEqual(self.hashes["leakage_report_sha256"], ss.sha256_file(self.paths["leakage_report"]))
        recomputed_manifest_hash = sha256_hex(
            canonical_json_bytes({key: value for key, value in self.manifest.items() if key != "manifest_hash"})
        )
        self.assertEqual(self.manifest["manifest_hash"], recomputed_manifest_hash)

    # 17. rebuilding with the same seed reproduces identical groups/splits/eligibility (deterministic groups)
    def test_rebuild_is_deterministic(self) -> None:
        result = ss.build_source_splits(ROOT, publish=False)
        self.assertEqual(result["manifest"]["record_counts"], self.manifest["record_counts"])

        rebuilt_split_by_id = {row["id"]: row["split"] for row in result["record_rows"]}
        original_split_by_id = {row["id"]: row["split"] for row in self.record_rows}
        self.assertEqual(rebuilt_split_by_id, original_split_by_id)

        rebuilt_group_by_id = {row["id"]: row["group_key"] for row in result["record_rows"]}
        original_group_by_id = {row["id"]: row["group_key"] for row in self.record_rows}
        self.assertEqual(rebuilt_group_by_id, original_group_by_id)

        rebuilt_eligibility_by_id = {row["id"]: row["eligibility"] for row in result["record_rows"]}
        original_eligibility_by_id = {row["id"]: row["eligibility"] for row in self.record_rows}
        self.assertEqual(rebuilt_eligibility_by_id, original_eligibility_by_id)

    # 18. training-target policy documents strategy D and never trains unavailable/ineligible as negative
    def test_training_target_policy_masks_unavailable_as_zero_weight(self) -> None:
        policy = ss.load_training_target_policy(ROOT)
        self.assertEqual(policy["strategy"], "D")
        self.assertEqual(policy["mask_policy"]["status_to_loss_weight"]["unavailable"], 0.0)
        self.assertEqual(policy["mask_policy"]["status_to_loss_weight"]["ineligible"], 0.0)
        self.assertEqual(policy["mask_policy"]["status_to_loss_weight"]["eligible"], 1.0)
        self.assertIn("never converted into a negative", policy["mask_policy"]["invariant"])
        self.assertEqual(policy["seed"], 20260722)


class SourceSplitUnitTests(unittest.TestCase):
    """Fast, isolated unit tests for the grouping/eligibility helpers."""

    def test_group_key_prefers_existing_group_id(self) -> None:
        record = {"id": "ambik:5", "source_dataset": "ambik", "group_id": "ambik:group:5", "command": "do it"}
        self.assertEqual(ss.compute_group_key(record), "group:ambik:group:5")

    def test_group_key_uses_at_suffix_lineage(self) -> None:
        first = {"id": "vague:abc123@1", "source_dataset": "vague", "group_id": None, "command": "hello there"}
        second = {"id": "vague:abc123@2", "source_dataset": "vague", "group_id": None, "command": "different text"}
        self.assertEqual(ss.compute_group_key(first), ss.compute_group_key(second))
        self.assertTrue(ss.compute_group_key(first).startswith("lineage:vague:"))

    def test_group_key_uses_frame_suffix_lineage(self) -> None:
        first = {"id": "vague:vid__x__frame_100", "source_dataset": "vague", "group_id": None, "command": "a"}
        second = {"id": "vague:vid__x__frame_200", "source_dataset": "vague", "group_id": None, "command": "b"}
        self.assertEqual(ss.compute_group_key(first), ss.compute_group_key(second))

    def test_group_key_falls_back_to_normalised_command(self) -> None:
        first = {"id": "indirect_requests:test:0", "source_dataset": "indirect_requests", "group_id": None, "command": "Help me, please!"}
        second = {"id": "indirect_requests:test:1", "source_dataset": "indirect_requests", "group_id": None, "command": "help me please"}
        self.assertEqual(ss.compute_group_key(first), ss.compute_group_key(second))

    def test_missing_field_yields_unavailable_not_ineligible_or_negative(self) -> None:
        record = {
            "source_dataset": "ambik",
            "label_eligibility": {"risk": True, "capability": False},
            "risk_level": None,
            "capability_status": None,
        }
        self.assertEqual(ss._eligibility_risk(record), "unavailable")
        self.assertEqual(ss._eligibility_capability(record), "ineligible")

    def test_context_blind_pairing_requires_group_partner(self) -> None:
        record = {"label_eligibility": {"context_benefit": True}}
        self.assertEqual(ss._eligibility_context_blind_pairing(record, group_size=1), "weakly_eligible")
        self.assertEqual(ss._eligibility_context_blind_pairing(record, group_size=2), "eligible")

    def test_leakage_detector_flags_injected_overlap(self) -> None:
        calibration_ids, calibration_commands = ss._load_calibration_ids_and_commands()
        overlapping_id = next(iter(calibration_ids))
        overlapping_command = next(iter(calibration_commands))
        planted = [
            {
                "id": overlapping_id,
                "source_dataset": "ambik",
                "command": overlapping_command,
                "label_eligibility": {},
            }
        ]
        report = ss.build_leakage_report(planted, [], root=ROOT)
        self.assertFalse(report["all_checks_passed"])
        self.assertIn(overlapping_id, report["checks"]["t13_calibration_id_overlap"])


if __name__ == "__main__":
    unittest.main()
