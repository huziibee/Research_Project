"""Tests for human-annotation ethics governance validation."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

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
        cls.repo_root = cls.paths.root
        cls.record_path = cls.repo_root / "configs" / "governance" / "human_annotation_governance.json"
        cls.evidence_path = (
            cls.repo_root
            / "docs"
            / "governance"
            / "evidence"
            / "ETHGOV-001_supervisor_only_determination.md"
        )
        with cls.record_path.open(encoding="utf-8") as handle:
            cls.record = json.load(handle)
        cls.report = (
            cls.repo_root / "docs" / "reports" / "ticket_T11_completion_report.md"
        ).read_text(encoding="utf-8")
        cls.t13 = (
            cls.repo_root
            / "cursor_plan"
            / "tickets"
            / "T13_manual_gold_guidelines_and_llm_authoring.md"
        ).read_text(encoding="utf-8")
        cls.t14 = (
            cls.repo_root
            / "cursor_plan"
            / "tickets"
            / "T14_double_annotation_agreement_and_adjudication.md"
        ).read_text(encoding="utf-8")

    def test_live_not_required_passes(self) -> None:
        errors = validate_ethics_determination(self.record, repo_root=self.repo_root)
        self.assertEqual(errors, [], msg="\n".join(errors))
        self.assertEqual(self.record["determination_status"], "not_required")
        self.assertEqual(self.record["determination_basis"], "supervisor_only_annotation")
        self.assertIs(self.record["ethics_clearance_required"], False)
        self.assertIs(self.record["ethics_waiver_required"], False)
        self.assertEqual(self.record["annotator_scope"], "project_supervisors_only")
        self.assertIs(self.record["external_annotators_permitted"], False)
        self.assertIs(self.record["reassessment_required_if_scope_changes"], True)
        self.assertTrue(self.record["collection_permitted"])
        self.assertEqual(derive_ticket_verdict(self.record), "PASS")
        self.assertTrue(derive_collection_permitted(self.record))
        self.assertTrue(self.evidence_path.is_file())

    def test_evidence_file_required(self) -> None:
        bad = copy.deepcopy(self.record)
        bad["determination_status_evidence"] = None
        bad["determination_evidence"]["evidence_path"] = None
        errors = validate_ethics_determination(bad, repo_root=self.repo_root)
        self.assertTrue(any("evidence" in e.lower() for e in errors))

    def test_missing_evidence_blocks(self) -> None:
        bad = copy.deepcopy(self.record)
        bad["determination_status_evidence"] = "docs/governance/evidence/does_not_exist.md"
        bad["determination_evidence"]["evidence_path"] = bad["determination_status_evidence"]
        errors = validate_ethics_determination(bad, repo_root=self.repo_root)
        self.assertTrue(any("does not exist" in e for e in errors))

    def test_wrong_evidence_id_blocks(self) -> None:
        bad = copy.deepcopy(self.record)
        bad["determination_evidence"]["evidence_id"] = "ETHGOV-999"
        errors = validate_ethics_determination(bad, repo_root=self.repo_root)
        self.assertTrue(any("ETHGOV-001" in e for e in errors))

    def test_wrong_basis_blocks(self) -> None:
        bad = copy.deepcopy(self.record)
        bad["determination_basis"] = "external_annotators"
        errors = validate_ethics_determination(bad, repo_root=self.repo_root)
        self.assertTrue(any("determination_basis" in e for e in errors))

    def test_clearance_required_true_blocks(self) -> None:
        bad = copy.deepcopy(self.record)
        bad["ethics_clearance_required"] = True
        errors = validate_ethics_determination(bad, repo_root=self.repo_root)
        self.assertTrue(any("ethics_clearance_required" in e for e in errors))

    def test_waiver_required_true_blocks(self) -> None:
        bad = copy.deepcopy(self.record)
        bad["ethics_waiver_required"] = True
        errors = validate_ethics_determination(bad, repo_root=self.repo_root)
        self.assertTrue(any("ethics_waiver_required" in e for e in errors))

    def test_external_annotators_permitted_true_blocks(self) -> None:
        bad = copy.deepcopy(self.record)
        bad["external_annotators_permitted"] = True
        bad["collection_permitted"] = False
        errors = validate_ethics_determination(bad, repo_root=self.repo_root)
        self.assertTrue(any("external annotators" in e.lower() for e in errors))
        self.assertFalse(derive_collection_permitted(bad))

    def test_reassessment_false_blocks(self) -> None:
        bad = copy.deepcopy(self.record)
        bad["reassessment_required_if_scope_changes"] = False
        errors = validate_ethics_determination(bad, repo_root=self.repo_root)
        self.assertTrue(any("reassessment_required_if_scope_changes" in e for e in errors))

    def test_non_boolean_values_block(self) -> None:
        bad = copy.deepcopy(self.record)
        bad["ethics_clearance_required"] = "false"
        errors = validate_ethics_determination(bad, repo_root=self.repo_root)
        self.assertTrue(any("Boolean" in e for e in errors))

    def test_external_annotator_scope_blocks(self) -> None:
        bad = copy.deepcopy(self.record)
        bad["annotator_scope"] = "includes_external_annotators"
        bad["collection_permitted"] = False
        errors = validate_ethics_determination(bad, repo_root=self.repo_root)
        self.assertTrue(any("annotator_scope" in e for e in errors))

    def test_collection_permission_limited_to_supervisor_scope(self) -> None:
        self.assertIn("supervisor", self.record["collection_permitted_semantics"].lower())
        self.assertNotIn("t13 technically ready", self.record["collection_permitted_semantics"].lower())

    def test_scope_drift_to_external_blocks(self) -> None:
        bad = copy.deepcopy(self.record)
        bad["external_annotators_permitted"] = True
        bad["external_annotator_recruitment"] = True
        bad["collection_permitted"] = True
        errors = validate_ethics_determination(bad, repo_root=self.repo_root)
        self.assertTrue(any("scope drift" in e.lower() or "external" in e.lower() for e in errors))
        self.assertTrue(any("collection_permitted must be false" in e for e in errors))
        self.assertFalse(derive_collection_permitted(bad))

    def test_historical_pending_remains_blocked(self) -> None:
        pending = {
            "governance_schema_version": "1.0.0",
            "determination_status": "pending",
            "determination_status_evidence": None,
            "collection_permitted": False,
            "role_pseudonyms": {
                "annotator_a": "ANN-A",
                "annotator_b": "ANN-B",
                "adjudicator": "ADJ-01",
                "author": "AUTHOR-01",
            },
            "compensation_policy": {"value": None, "status": "pending_human_confirmation"},
            "retention_period": {"value": None, "status": "pending_human_confirmation"},
            "deletion_policy": {"value": None, "status": "pending_human_confirmation"},
            "informed_consent_required": {"value": None, "status": "pending_human_confirmation"},
            "personal_data_collected": {"value": None, "status": "pending_human_confirmation"},
            "responsible_authority": {"value": None, "status": "pending_human_confirmation"},
            "institution": {"value": None, "status": "pending_human_confirmation"},
            "identity_mapping_store": {"value": None, "status": "pending_human_confirmation"},
        }
        self.assertEqual(validate_ethics_determination(pending), [])
        self.assertEqual(derive_ticket_verdict(pending), "BLOCKED")
        self.assertFalse(derive_collection_permitted(pending))

    def test_approval_required_without_evidence_is_invalid(self) -> None:
        bad = dict(self.record)
        bad["determination_status"] = "approval_required"
        bad["determination_status_evidence"] = None
        bad["collection_permitted"] = False
        errors = validate_ethics_determination(bad)
        self.assertTrue(any("evidence" in e for e in errors))

    def test_approval_required_with_evidence_pass_collection_blocked(self) -> None:
        record = {
            "governance_schema_version": "1.0.0",
            "determination_status": "approval_required",
            "determination_status_evidence": "docs/governance/evidence/ethics_approval_required.pdf",
            "collection_permitted": False,
            "role_pseudonyms": self.record["role_pseudonyms"],
            "compensation_policy": {"value": None, "status": "pending_human_confirmation"},
            "retention_period": {"value": None, "status": "pending_human_confirmation"},
            "deletion_policy": {"value": None, "status": "pending_human_confirmation"},
            "informed_consent_required": {"value": None, "status": "pending_human_confirmation"},
            "personal_data_collected": {"value": None, "status": "pending_human_confirmation"},
            "responsible_authority": {"value": None, "status": "pending_human_confirmation"},
            "institution": {"value": None, "status": "pending_human_confirmation"},
            "identity_mapping_store": {"value": None, "status": "pending_human_confirmation"},
        }
        self.assertEqual(validate_ethics_determination(record), [])
        self.assertEqual(derive_ticket_verdict(record), "PASS")
        self.assertFalse(derive_collection_permitted(record))

    def test_approved_permits_collection(self) -> None:
        record = {
            "governance_schema_version": "1.0.0",
            "determination_status": "approved",
            "determination_status_evidence": "docs/governance/evidence/ethics_approved.pdf",
            "collection_permitted": True,
            "role_pseudonyms": self.record["role_pseudonyms"],
            "compensation_policy": {"value": None, "status": "pending_human_confirmation"},
            "retention_period": {"value": None, "status": "pending_human_confirmation"},
            "deletion_policy": {"value": None, "status": "pending_human_confirmation"},
            "informed_consent_required": {"value": None, "status": "pending_human_confirmation"},
            "personal_data_collected": {"value": None, "status": "pending_human_confirmation"},
            "responsible_authority": {"value": None, "status": "pending_human_confirmation"},
            "institution": {"value": None, "status": "pending_human_confirmation"},
            "identity_mapping_store": {"value": None, "status": "pending_human_confirmation"},
        }
        self.assertEqual(validate_ethics_determination(record), [])
        self.assertEqual(derive_ticket_verdict(record), "PASS")
        self.assertTrue(derive_collection_permitted(record))

    def test_t11_report_avoids_approved_exempt_wording(self) -> None:
        lowered = self.report.lower()
        self.assertIn("pass", lowered)
        self.assertIn("not required", lowered)
        self.assertNotIn("ethics approved", lowered)
        self.assertNotIn("ethics approval granted", lowered)
        self.assertRegex(lowered, r"not\*?\*? an ethics approval or exemption")

    def test_t13_t14_not_marked_complete_or_collection_started(self) -> None:
        self.assertIn("Collection started:** no", self.t13)
        self.assertIn("technically not ready", self.t13.lower())
        self.assertIn("Collection started:** no", self.t14)
        self.assertNotIn("**Status:** COMPLETE", self.t13)
        self.assertNotIn("**Status:** COMPLETE", self.t14)

    def test_selected_model_remains_null(self) -> None:
        register_path = self.repo_root / "configs" / "licences" / "model_licence_register.json"
        with register_path.open(encoding="utf-8") as handle:
            register = json.load(handle)
        self.assertIsNone(register["selected_model"])

    def test_stable_pseudonyms_documented(self) -> None:
        pseudonyms = self.record["role_pseudonyms"]
        self.assertEqual(pseudonyms["annotator_a"], "ANN-A")
        self.assertEqual(pseudonyms["annotator_b"], "ANN-B")
        self.assertEqual(pseudonyms["adjudicator"], "ADJ-01")
        self.assertEqual(pseudonyms["author"], "AUTHOR-01")


if __name__ == "__main__":
    unittest.main()
