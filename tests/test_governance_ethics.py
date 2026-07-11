"""Tests for human-annotation ethics governance validation."""

from __future__ import annotations

import json
import unittest

from ambiguity_manager.governance.ethics import (
    derive_collection_permitted,
    derive_ticket_verdict,
    validate_ethics_determination,
)
from ambiguity_manager.paths import ProjectPaths


class TestGovernanceEthics(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.paths = ProjectPaths.from_repo_root()
        cls.record_path = cls.paths.root / "configs" / "governance" / "human_annotation_governance.json"
        with cls.record_path.open(encoding="utf-8") as handle:
            cls.record = json.load(handle)

    def test_initial_status_pending(self) -> None:
        self.assertEqual(self.record["determination_status"], "pending")
        self.assertIsNone(self.record["determination_status_evidence"])
        self.assertFalse(self.record["collection_permitted"])

    def test_pending_blocks_t11_pass(self) -> None:
        self.assertEqual(derive_ticket_verdict(self.record), "BLOCKED")

    def test_pending_blocks_collection(self) -> None:
        self.assertFalse(derive_collection_permitted(self.record))

    def test_approval_required_without_evidence_is_invalid(self) -> None:
        bad = dict(self.record)
        bad["determination_status"] = "approval_required"
        bad["determination_status_evidence"] = None
        errors = validate_ethics_determination(bad)
        self.assertTrue(any("evidence" in e for e in errors))

    def test_approval_required_with_evidence_pass_collection_blocked(self) -> None:
        record = dict(self.record)
        record["determination_status"] = "approval_required"
        record["determination_status_evidence"] = "docs/governance/evidence/ethics_approval_required.pdf"
        record["collection_permitted"] = derive_collection_permitted(record)
        self.assertEqual(derive_ticket_verdict(record), "PASS")
        self.assertFalse(record["collection_permitted"])

    def test_approved_permits_collection(self) -> None:
        record = dict(self.record)
        record["determination_status"] = "approved"
        record["determination_status_evidence"] = "docs/governance/evidence/ethics_approved.pdf"
        record["collection_permitted"] = derive_collection_permitted(record)
        self.assertEqual(derive_ticket_verdict(record), "PASS")
        self.assertTrue(record["collection_permitted"])

    def test_no_invented_defaults(self) -> None:
        compensation = self.record["compensation_policy"]
        self.assertEqual(compensation["value"], None)
        self.assertEqual(compensation["status"], "pending_human_confirmation")

    def test_stable_pseudonyms_documented(self) -> None:
        pseudonyms = self.record["role_pseudonyms"]
        self.assertEqual(pseudonyms["annotator_a"], "ANN-A")
        self.assertEqual(pseudonyms["annotator_b"], "ANN-B")
        self.assertEqual(pseudonyms["adjudicator"], "ADJ-01")
        self.assertEqual(pseudonyms["author"], "AUTHOR-01")


if __name__ == "__main__":
    unittest.main()
