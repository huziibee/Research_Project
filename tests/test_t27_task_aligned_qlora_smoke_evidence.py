"""Evidence lock for the blocked T27 task-aligned QLoRA live smoke."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "configs/model/evidence/t27_task_aligned_qlora_smoke.json"
REPORT = ROOT / "docs/reports/ticket_T27_task_aligned_qlora_smoke.md"
IDENTITIES = ROOT / "configs/model/selected_identities_v1.json"
PRIOR = ROOT / "configs/model/evidence/qlora_smoke_v1/qlora_smoke_result.json"


class TaskAlignedQloraSmokeEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        cls.identities = json.loads(IDENTITIES.read_text(encoding="utf-8"))

    def test_evidence_and_report_exist(self) -> None:
        self.assertTrue(EVIDENCE.is_file())
        self.assertTrue(REPORT.is_file())
        self.assertTrue(PRIOR.is_file())

    def test_live_run_identity(self) -> None:
        self.assertEqual(self.evidence["run_id"], "t12-qlora-task-aligned-20260723T074715Z-991732e")
        self.assertEqual(self.evidence["slurm_job_id"], "6059")
        self.assertEqual(self.evidence["node"], "mscluster111")
        self.assertEqual(self.evidence["mode"], "real_cluster_training")
        self.assertEqual(self.evidence["operator_verify"], "VERIFY_PASSED")

    def test_statuses_blocked_on_structured_output(self) -> None:
        statuses = self.evidence["statuses"]
        self.assertEqual(statuses["mechanics_status"], "PASS")
        self.assertEqual(statuses["task_aligned_training_status"], "PASS")
        self.assertEqual(statuses["structured_output_smoke_status"], "BLOCKED")
        self.assertEqual(statuses["ticket_status"], "BLOCKED")
        self.assertFalse(self.evidence["t28_may_begin"])

    def test_full_resume_and_masks(self) -> None:
        resume = self.evidence["checkpoint_resume"]
        self.assertTrue(resume["full_resume_ok"])
        self.assertTrue(resume["optimiser_restore_ok"])
        self.assertTrue(resume["scheduler_restore_ok"])
        self.assertTrue(resume["rng_restore_ok"])
        self.assertTrue(resume["data_position_restore_ok"])
        self.assertTrue(self.evidence["training"]["structured_targets_used"])
        self.assertTrue(self.evidence["training"]["real_token_masks_used"])
        self.assertFalse(self.evidence["training"]["command_reconstruction"])

    def test_structured_zero_accepted(self) -> None:
        structured = self.evidence["structured_output"]
        self.assertEqual(structured["accepted_count"], 0)
        self.assertEqual(structured["adapter_differs_from_base_count"], 4)
        self.assertTrue(structured["braces_only_acceptance_forbidden"])

    def test_identities_unchanged(self) -> None:
        self.assertEqual(
            self.identities["selected_base_model"],
            "Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218",
        )
        self.assertIsNone(self.identities["selected_adapter"])
        self.assertIsNone(self.identities["selected_model_strategy"])
        self.assertFalse(self.identities["valid_for_official_use"])
        self.assertFalse(self.evidence["adapter"]["selected_adapter"])
        self.assertTrue(self.evidence["adapter"]["technical_smoke_only"])
        self.assertFalse(self.evidence["adapter"]["committed"])


if __name__ == "__main__":
    unittest.main()
