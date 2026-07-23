from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class T27DEvidenceTests(unittest.TestCase):
    def test_job10065_matrix_reconciles(self) -> None:
        evidence = json.loads((ROOT / "configs/model/evidence/t27d_job10065_task_failure_matrix.json").read_text())
        self.assertEqual(evidence["terminal_task_calls"], 120)
        for mode in ("base", "adapter"):
            self.assertEqual(sum(v["attempted"] for v in evidence["task_metrics"][mode].values()), 60)
            self.assertTrue(all(v["constraint_initialised"] == v["attempted"] for v in evidence["task_metrics"][mode].values()))

    def test_fresh_sets_are_frozen_and_disjoint(self) -> None:
        diagnostic = json.loads((ROOT / "data/development/t27d_diagnostic_dev_v1/manifest.json").read_text())
        sealed = json.loads((ROOT / "data/development/t27d_final_smoke_v1/manifest.json").read_text())
        self.assertEqual(diagnostic["record_count"], 16)
        self.assertEqual(sealed["record_count"], 12)
        self.assertTrue(set(diagnostic["record_ids"]).isdisjoint(sealed["record_ids"]))
        self.assertEqual(len(diagnostic["group_keys"]), len(set(diagnostic["group_keys"])))
        self.assertEqual(len(sealed["group_keys"]), len(set(sealed["group_keys"])))
        self.assertGreaterEqual(len(set(sealed["datasets"])), 3)
        self.assertEqual(sealed["seal_status"], "sealed_before_execution")


if __name__ == "__main__":
    unittest.main()
