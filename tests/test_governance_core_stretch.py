"""Tests for core/stretch policy and remaining governance artefacts."""

from __future__ import annotations

import json
import unittest

from ambiguity_manager.governance.core_stretch import validate_core_stretch_policy
from ambiguity_manager.governance.model_licence import validate_model_licence_register
from ambiguity_manager.governance.paths import is_tracked_governance_log_path
from ambiguity_manager.governance.role_overlap import validate_role_overlap_entry
from ambiguity_manager.paths import ProjectPaths


class TestGovernanceCoreStretch(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.paths = ProjectPaths.from_repo_root()
        with (cls.paths.root / "configs" / "governance" / "core_stretch_policy.json").open(
            encoding="utf-8"
        ) as handle:
            cls.policy = json.load(handle)

    def test_mandatory_core_tickets_exact(self) -> None:
        expected = [
            "T10", "T11", "T12", "T13", "T14", "T15", "T16", "T17", "T18", "T19",
            "T20", "T21", "T22", "T23", "T24", "T26", "T27", "T28", "T29", "T30",
            "T31", "T32", "T33", "T36", "T37", "T38",
        ]
        self.assertEqual(self.policy["mandatory_core_tickets"], expected)

    def test_stretch_tickets(self) -> None:
        self.assertEqual(self.policy["stretch_nonblocking_tickets"], ["T25", "T34", "T35"])

    def test_seven_systems_mandatory(self) -> None:
        self.assertTrue(self.policy["seven_systems_mandatory"])
        self.assertEqual(len(self.policy["mandatory_system_ids"]), 7)

    def test_core_ticket_cannot_use_blocked_noncritical(self) -> None:
        bad = json.loads(json.dumps(self.policy))
        bad["ticket_status_overrides"] = {"T11": "BLOCKED_NONCRITICAL"}
        errors = validate_core_stretch_policy(bad)
        self.assertTrue(any("BLOCKED_NONCRITICAL" in e for e in errors))

    def test_model_register_no_selected_model(self) -> None:
        with (self.paths.root / "configs" / "licences" / "model_licence_register.json").open(
            encoding="utf-8"
        ) as handle:
            register = json.load(handle)
        self.assertIsNone(register["selected_model"])
        self.assertEqual(validate_model_licence_register(register), [])

    def test_governance_logs_tracked_paths(self) -> None:
        for name in (
            "generative_ai_use_log.jsonl",
            "decision_log.jsonl",
            "deviation_log.jsonl",
            "protected_access_log.jsonl",
            "role_overlap_log.jsonl",
        ):
            rel = f"docs/governance/logs/{name}"
            self.assertTrue(is_tracked_governance_log_path(rel))
            self.assertTrue((self.paths.root / rel).is_file())

    def test_author_cannot_annotate_same_record(self) -> None:
        errors = validate_role_overlap_entry(
            {
                "record_id": "rec-001",
                "roles": ["AUTHOR-01", "ANN-A"],
                "overlap_type": "author_annotator",
            }
        )
        self.assertTrue(errors)

    def test_author_adjudicator_requires_approval_ref(self) -> None:
        errors = validate_role_overlap_entry(
            {
                "record_id": "rec-001",
                "roles": ["AUTHOR-01", "ADJ-01"],
                "overlap_type": "author_adjudicator",
                "authority_approval_ref": None,
            }
        )
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
