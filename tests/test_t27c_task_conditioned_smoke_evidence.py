"""T27C live evidence skeleton (pending until cluster run)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

EVIDENCE = ROOT / "configs/model/evidence/t27c_task_conditioned_qlora_smoke.json"
T27_EVIDENCE = ROOT / "configs/model/evidence/t27_task_aligned_qlora_smoke.json"
T27B_EVIDENCE = ROOT / "configs/model/evidence/t27b_structured_emission_recovery.json"


class T27CTaskConditionedSmokeEvidenceTests(unittest.TestCase):
    def test_prior_evidence_retained(self) -> None:
        self.assertTrue(T27_EVIDENCE.is_file())
        self.assertTrue(T27B_EVIDENCE.is_file())
        t27 = json.loads(T27_EVIDENCE.read_text(encoding="utf-8"))
        t27b = json.loads(T27B_EVIDENCE.read_text(encoding="utf-8"))
        self.assertIn("6059", str(t27.get("slurm_job_id") or t27.get("job_id") or "") + json.dumps(t27))
        self.assertIn("6382", str(t27b.get("slurm_job_id") or t27b.get("job_id") or "") + json.dumps(t27b))

    def test_t27c_evidence_pending_or_well_formed(self) -> None:
        if not EVIDENCE.is_file():
            self.skipTest("T27C live evidence not yet written (pending cluster run)")
        payload = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        for key in (
            "provider_id",
            "run_id",
            "mode",
            "selected_adapter",
            "valid_for_official_use",
            "pass_threshold_evaluation",
        ):
            self.assertIn(key, payload)
        self.assertEqual(payload["provider_id"], "qlora_task_conditioned_smoke_v1")
        self.assertIsNone(payload["selected_adapter"])
        self.assertFalse(payload["valid_for_official_use"])
        self.assertEqual(payload.get("mode"), "real_cluster_training")


if __name__ == "__main__":
    unittest.main()
