from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class T27CRuntimeRecoveryEvidenceTests(unittest.TestCase):
    def test_evidence_is_honest_and_preserves_official_nulls(self) -> None:
        payload = json.loads((ROOT / "configs/model/evidence/t27c_runtime_recovery.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["job_9479"]["root_cause_classification"], "insufficient observability")
        self.assertFalse(payload["job_9479"]["genuine_generation_hang"])
        self.assertEqual(payload["adapter_reuse"]["status"], "identity_mismatch")
        self.assertIsNone(payload["adapter_reuse"]["selected_adapter"])
        self.assertIsNone(payload["selected_adapter"] if "selected_adapter" in payload else None)
        self.assertFalse(payload["t28_may_begin"])

    def test_workload_reconciles(self) -> None:
        payload = json.loads((ROOT / "configs/model/evidence/t27c_runtime_recovery.json").read_text(encoding="utf-8"))
        frozen = payload["frozen_data"]
        self.assertEqual(frozen["sealed_task_calls_per_mode"] * 2, frozen["sealed_total_task_calls"])
        self.assertEqual(frozen["sealed_records"], 12)


if __name__ == "__main__":
    unittest.main()
