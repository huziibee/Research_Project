"""T27B target/schema compatibility audit tests (CPU-only)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.model.prediction_contract import MODEL_OUTPUT_REQUIRED_FIELDS  # noqa: E402


class T27BTargetSchemaAuditTests(unittest.TestCase):
    def test_policy_covers_all_25_fields(self) -> None:
        policy = json.loads(
            (ROOT / "configs/model/full_schema_envelope_policy_v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(policy["envelope_id"], "full_schema_envelope_v1")
        decisions = policy["field_decisions"]
        self.assertEqual(set(decisions), set(MODEL_OUTPUT_REQUIRED_FIELDS))
        always = set(policy["always_masked_fields"])
        self.assertTrue(
            {
                "unresolved_slots",
                "supporting_evidence",
                "resolved_slots",
                "resolution_method",
                "resolution_evidence",
                "context_sampling_uncertainty",
            }.issubset(always)
        )
        mins = policy["minimum_useful_supervision"]
        self.assertTrue(mins["frozen_before_live_results"])
        self.assertGreaterEqual(float(mins["min_mean_supervised_token_percentage"]), 12.0)
        thresholds = policy["pass_thresholds"]
        self.assertEqual(int(thresholds["sealed_final_count"]), 8)
        self.assertEqual(int(thresholds["unsupported_commitment_accepted_max"]), 0)

    def test_coverage_audit_25_fields_and_job6059_failures(self) -> None:
        audit = json.loads(
            (ROOT / "configs/model/t27b_production_schema_coverage_v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(audit["audit_version"], "1.0.0")
        fields = {item["field_path"] for item in audit["fields"]}
        self.assertEqual(fields, set(MODEL_OUTPUT_REQUIRED_FIELDS))
        failures = audit["job6059_failure_classification"]
        self.assertEqual(len(failures), 8)
        roles = {(item["record_id"], item["role"]) for item in failures}
        expected = {
            ("clara:1003", "base"),
            ("clara:1003", "adapter"),
            ("clara:1180", "base"),
            ("clara:1180", "adapter"),
            ("clara:1349", "base"),
            ("clara:1349", "adapter"),
            ("codraw_icr_v2:4784", "base"),
            ("codraw_icr_v2:4784", "adapter"),
        }
        self.assertEqual(roles, expected)
        retained = audit["retained_evidence"]
        self.assertEqual(retained["job_id"], 6059)

    def test_human_audit_report_exists(self) -> None:
        path = ROOT / "docs/reports/ticket_T27B_target_schema_compatibility_audit.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("full_schema_envelope_v1", text)
        self.assertIn("T27B live training/eval has not been run", text)
        self.assertIn("clara:1003", text)


if __name__ == "__main__":
    unittest.main()
