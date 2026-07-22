"""CPU-only validation tests for T12 Stage D-Final final live smoke evidence."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

from ambiguity_manager.model.cluster.path_policy import scan_forbidden_paths
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root
FINAL_EVIDENCE_REL = "configs/model/evidence/t12_d_final_live_smoke_final.json"
FINAL_REPORT_REL = "docs/reports/ticket_T12_D_final_live_smoke_final.md"
BASELINE_EVIDENCE_REL = "configs/model/evidence/t12_d_final_live_smoke.json"
ETHICS_REL = "configs/governance/human_annotation_governance.json"
CORRECTION_SHA = "f0cf937fef188e9d440bd573a418914889ad9e1a"
BASELINE_SHA = "02f43622b2db90a7e5ed2662a48a0752a9a0e8cc"
CONTAINER_SHA = "d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1"
ARCHIVE_SHA = "32990cf09565a7722401c205fd05259606bdd81cb6ae220eaa086525dff6b383"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _load(relpath: str) -> dict:
    return json.loads((ROOT / relpath).read_text(encoding="utf-8"))


class T12DFinalLiveSmokeFinalEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = _load(FINAL_EVIDENCE_REL)
        cls.baseline = _load(BASELINE_EVIDENCE_REL)
        cls.report = (ROOT / FINAL_REPORT_REL).read_text(encoding="utf-8")
        cls.ethics = _load(ETHICS_REL)
        cls.evidence_text = (ROOT / FINAL_EVIDENCE_REL).read_text(encoding="utf-8")

    def test_final_and_baseline_evidence_exist(self) -> None:
        self.assertTrue((ROOT / FINAL_EVIDENCE_REL).is_file())
        self.assertTrue((ROOT / FINAL_REPORT_REL).is_file())
        self.assertTrue((ROOT / BASELINE_EVIDENCE_REL).is_file())

    def test_baseline_job_3974_preserved_and_unchanged_identity(self) -> None:
        baseline_meta = self.evidence["baseline_job_3974"]
        self.assertEqual(baseline_meta["slurm_job_id"], "3974")
        self.assertEqual(baseline_meta["source_commit_sha"], BASELINE_SHA)
        self.assertEqual(baseline_meta["status"], "BLOCKED")
        self.assertEqual(baseline_meta["records_accepted"], 0)
        self.assertEqual(self.baseline["run_identity"]["slurm_job_id"], "3974")
        self.assertEqual(self.baseline["run_status"]["status"], "BLOCKED")
        self.assertEqual(self.baseline["record_results"]["records_accepted"], 0)

    def test_correction_commit_and_source_identity(self) -> None:
        self.assertEqual(self.evidence["correction_commit"]["sha"], CORRECTION_SHA)
        self.assertEqual(self.evidence["source_transfer"]["local_commit_sha"], CORRECTION_SHA)
        self.assertEqual(self.evidence["source_transfer"]["method"], "git_archive")
        self.assertEqual(self.evidence["source_transfer"]["archive_sha256"], ARCHIVE_SHA)
        self.assertRegex(ARCHIVE_SHA, SHA256_RE)

    def test_container_and_model_match(self) -> None:
        self.assertTrue(self.evidence["container_integrity"]["match"])
        self.assertEqual(self.evidence["container_integrity"]["observed_sha256"], CONTAINER_SHA)
        self.assertEqual(self.evidence["model_identity"]["model_repository"], "Qwen/Qwen3-8B")
        self.assertEqual(
            self.evidence["model_identity"]["model_revision"],
            "b968826d9c46dd6066d109eabc6255188de91218",
        )

    def test_governance_invariants(self) -> None:
        gov = self.evidence["governance_state"]
        self.assertEqual(gov["t11_status"], "PASS")
        self.assertEqual(gov["ethics_determination_status"], "not_required")
        self.assertFalse(gov["external_annotators_permitted"])
        self.assertIsNone(gov["selected_model"])
        self.assertFalse(gov["protected_data_used"])
        self.assertFalse(gov["research_pool_used"])
        self.assertEqual(self.ethics["determination_status"], "not_required")

    def test_response_mode_and_engine(self) -> None:
        probe = self.evidence["response_mode_probe"]
        self.assertEqual(probe["selected_response_mode"], "enable_thinking_false")
        self.assertEqual(probe["response_mode_verification_status"], "verified_for_run")
        self.assertFalse(probe["default"]["passed"])
        self.assertTrue(probe["enable_thinking_false"]["passed"])
        self.assertEqual(self.evidence["generation_execution"]["engine_start_count"], 1)

    def test_generation_call_accounting(self) -> None:
        gen = self.evidence["generation_execution"]
        self.assertEqual(gen["probe_generation_call_count"], 2)
        self.assertEqual(gen["record_generation_call_count"], 9)
        self.assertEqual(gen["total_generation_call_count"], 11)
        self.assertEqual(
            gen["total_generation_call_count"],
            gen["probe_generation_call_count"] + gen["record_generation_call_count"],
        )
        self.assertEqual(gen["runner_reported_generation_call_count"], 2)
        self.assertEqual(gen["runner_generation_count_semantics"], "probe_calls_only")

    def test_three_accepted_one_blocked_stop_rule(self) -> None:
        records = self.evidence["record_results"]
        self.assertEqual(records["records_attempted"], 4)
        self.assertEqual(records["records_accepted"], 3)
        self.assertEqual(records["records_rejected_after_attempts"], 1)
        self.assertEqual(records["schema_valid_accepted_count"], 3)
        self.assertEqual(records["canonical_schema_v2_valid_accepted_count"], 3)
        self.assertEqual(records["unsupported_commitment_count_on_accepted"], 0)
        self.assertEqual(records["raw_attempt_retention_count"], 9)
        self.assertEqual(self.evidence["run_status"]["status"], "BLOCKED")
        self.assertTrue(self.evidence["run_status"]["round_trip_defect_resolved"])
        stop = self.evidence["stop_rule"]
        self.assertTrue(stop["triggered"])
        self.assertFalse(stop["further_d_final_corrections_permitted"])
        self.assertEqual(stop["qwen3_8b_zero_shot_under_frozen_contract"], "unsuitable")

    def test_dfinal_004_unsupported_commitment_failure(self) -> None:
        rec = self.evidence["record_results"]["per_record"]["dfinal-004"]
        self.assertEqual(rec["final_status"], "rejected_after_attempts")
        self.assertEqual(rec["attempts_used"], 3)
        self.assertEqual(
            rec["failure_categories"],
            [
                "unsupported_silent_commitment",
                "unsupported_silent_commitment",
                "unsupported_silent_commitment",
            ],
        )

    def test_semantic_correctness_not_evaluated(self) -> None:
        self.assertEqual(self.evidence["semantic_correctness_status"], "not_evaluated")

    def test_manifest_verification_passed(self) -> None:
        mv = self.evidence["manifest_verification"]
        self.assertTrue(mv["performed"])
        self.assertTrue(mv["passed"])
        self.assertTrue(mv["all_listed_hashes_matched"])

    def test_no_forbidden_paths_or_credentials(self) -> None:
        self.assertEqual(scan_forbidden_paths(self.evidence), [])
        for pattern in (
            r"\bmbangie\b",
            r"\bhuzii\b",
            r"C:\\Users\\",
            r"/home-mscluster/",
            r"password\s*=",
            r"BEGIN (RSA|OPENSSH) PRIVATE KEY",
        ):
            self.assertIsNone(re.search(pattern, self.evidence_text))
            self.assertIsNone(re.search(pattern, self.report))

    def test_report_records_blocked_and_stop_rule(self) -> None:
        self.assertIn("BLOCKED", self.report)
        self.assertIn("stop rule", self.report.lower())
        self.assertIn(CORRECTION_SHA, self.report)
        self.assertIn("3998", self.report)
        self.assertIn("unsuitable", self.report.lower())

    def test_import_isolation(self) -> None:
        for module_name in (
            "ambiguity_manager.model.cluster.identities",
            "ambiguity_manager.model.cluster.path_policy",
        ):
            self.assertIsNotNone(importlib.util.find_spec(module_name))
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("vllm", sys.modules)
        self.assertNotIn("transformers", sys.modules)


if __name__ == "__main__":
    unittest.main()
