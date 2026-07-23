"""Evidence lock for T27B structured-emission recovery (job 6382)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = REPO_ROOT / "configs" / "model" / "evidence" / "t27b_structured_emission_recovery.json"
T27_EVIDENCE = REPO_ROOT / "configs" / "model" / "evidence" / "t27_task_aligned_qlora_smoke.json"
IDENTITIES = REPO_ROOT / "configs" / "model" / "selected_identities_v1.json"


class T27BStructuredEmissionRecoveryEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        cls.t27 = json.loads(T27_EVIDENCE.read_text(encoding="utf-8"))
        cls.identities = json.loads(IDENTITIES.read_text(encoding="utf-8"))

    def test_run_and_job_locked(self) -> None:
        self.assertEqual(
            self.evidence["run_id"],
            "t12-qlora-emission-recovery-20260723T090929Z-3ae20c7",
        )
        self.assertEqual(self.evidence["slurm_job_id"], "6382")
        self.assertEqual(self.evidence["source_commit"], "3ae20c776346352f46e2d9696b0758132c002114")
        self.assertEqual(self.evidence["mode"], "real_cluster_training")
        self.assertEqual(self.evidence["operator_verify"], "VERIFY_PASSED")

    def test_job6059_evidence_preserved(self) -> None:
        retained = self.evidence["retained_t27_job6059_evidence"]
        self.assertEqual(retained["slurm_job_id"], "6059")
        self.assertEqual(
            retained["run_id"],
            "t12-qlora-task-aligned-20260723T074715Z-991732e",
        )
        self.assertFalse(retained["overwritten"])
        self.assertEqual(self.t27["slurm_job_id"], "6059")
        self.assertEqual(self.t27["statuses"]["ticket_status"], "BLOCKED")

    def test_mechanics_pass_structured_blocked(self) -> None:
        statuses = self.evidence["statuses"]
        self.assertEqual(statuses["mechanics_status"], "PASS")
        self.assertEqual(statuses["data_status"], "PASS")
        self.assertEqual(statuses["supervision_density_status"], "PASS")
        self.assertEqual(statuses["structured_emission_status"], "BLOCKED")
        self.assertEqual(statuses["ticket_status"], "BLOCKED")
        self.assertFalse(self.evidence["t28_may_begin"])

    def test_structured_counts(self) -> None:
        adapter = self.evidence["structured_output"]["adapter"]
        self.assertEqual(adapter["attempted"], 8)
        self.assertEqual(adapter["final_accepted"], 0)
        self.assertEqual(adapter["schema_valid"], 0)
        self.assertEqual(adapter["parse_valid"], 1)
        self.assertEqual(
            self.evidence["structured_output"]["adapter_differs_from_base_count"],
            8,
        )

    def test_identities_unchanged(self) -> None:
        expected = "Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218"
        self.assertEqual(self.evidence["selected_base_model"], expected)
        self.assertIsNone(self.evidence["identities_unchanged"]["selected_adapter"])
        self.assertIsNone(self.evidence["identities_unchanged"]["selected_model_strategy"])
        self.assertFalse(self.evidence["identities_unchanged"]["valid_for_official_use"])
        self.assertEqual(self.identities.get("selected_base_model"), expected)
        self.assertIsNone(self.identities.get("selected_adapter"))
        self.assertIsNone(self.identities.get("selected_model_strategy"))

    def test_resume_and_density(self) -> None:
        resume = self.evidence["checkpoint_resume"]
        self.assertTrue(resume["full_resume_ok"])
        density = self.evidence["training"]["supervised_token_diagnostics"]
        self.assertGreaterEqual(float(density["mean_supervised_token_percentage"]), 12.0)
        self.assertTrue(density["meets_minimum_useful_supervision"])


if __name__ == "__main__":
    unittest.main()
