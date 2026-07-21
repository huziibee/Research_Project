"""Tests for deviation log validation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ambiguity_manager.governance.deviations import (
    load_deviation_log,
    validate_deviation_entry,
    validate_deviation_log,
)
from ambiguity_manager.governance.validation import validate_repository_governance
from ambiguity_manager.paths import ProjectPaths


def _valid_entry() -> dict:
    return {
        "deviation_id": "DEV-20260711-001",
        "date": "2026-07-11",
        "status": "accepted",
        "change_type": "execution_order_exception",
        "approver": "Mohammed Bangie / AUTHOR-01, project owner",
        "approval_basis": "Explicit human approval in the project execution workflow",
        "protocol_version_before": "research_contract_v1.0.0; T11 governance infrastructure complete",
        "protocol_version_after": "unchanged (execution-order exception only)",
        "affected_tickets": ["T11", "T12"],
        "affected_artefacts": [
            "docs/decisions/DEV-20260711-001_pre_t12_execution_order_deviation.md",
            "cursor_plan/tickets/T12_local_text_model_and_training_stack_setup.md",
            "cursor_plan/05_master_execution_plan.md",
            "docs/reports/ticket_T11_completion_report.md",
        ],
        "summary": (
            "Authorise narrow T12 local RTX 3070 hardware/model work on synthetic or "
            "non-protected schema-v2 fixtures while T11 remains BLOCKED."
        ),
        "rationale": (
            "T11 infrastructure is complete but ethics determination_status remains pending "
            "with collection_permitted false. T12 scope is limited to RTX 3070 facts, local "
            "stack setup, licence review, synthetic/non-protected schema-v2 inference tests, "
            "latency/VRAM/repeatability measurement, and a minimal adapter-load probe without "
            "research-data training. T12 must not use protected data, collect annotations, "
            "fine-tune on research datasets, begin T13, begin T14, or weaken licence gates. "
            "T12 completion does not satisfy T11."
        ),
        "evidence": [
            "docs/reports/ticket_T11_completion_report.md",
            "configs/governance/human_annotation_governance.json",
            "cursor_plan/tickets/T12_local_text_model_and_training_stack_setup.md",
            "configs/research/research_contract_v1.json",
        ],
        "risk": "Scope creep into annotation or research-dataset training.",
        "required_reruns": "None; reassess governance before T13/T14.",
        "protected_test_implications": "None; T12 must not access protected test data.",
        "preservation_of_prior_outputs": (
            "T00-T11 artefacts, T11 BLOCKED verdict, ethics pending state with "
            "collection_permitted false, and licence null-permission gates remain unchanged."
        ),
        "ethics_disclaimer": (
            "The institutional ethics determination remains pending. This deviation does "
            "not constitute or imply institutional ethics approval."
        ),
    }


class TestGovernanceDeviations(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.paths = ProjectPaths.from_repo_root()
        cls.repo_root = cls.paths.root

    def test_valid_current_deviation(self) -> None:
        log_path = self.repo_root / "docs/governance/logs/deviation_log.jsonl"
        entries, parse_errors = load_deviation_log(log_path)
        self.assertEqual(parse_errors, [])
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["deviation_id"], "DEV-20260711-001")
        self.assertEqual(entries[0]["change_type"], "execution_order_exception")
        self.assertEqual(entries[1]["deviation_id"], "DEV-20260721-001")
        self.assertEqual(entries[1]["change_type"], "deviation_closure")
        self.assertEqual(entries[1]["closes_deviation_id"], "DEV-20260711-001")
        self.assertIn("ETHGOV-001", entries[1]["closure_basis"])
        errors = validate_deviation_log(entries, repo_root=self.repo_root, parse_errors=parse_errors)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_closure_retains_historical_authority(self) -> None:
        log_path = self.repo_root / "docs/governance/logs/deviation_log.jsonl"
        entries, _ = load_deviation_log(log_path)
        historical = entries[0]
        self.assertEqual(historical["status"], "accepted")
        self.assertIn("pending", historical["ethics_disclaimer"].lower())
        closure_doc = (
            self.repo_root / "docs/decisions/DEV-20260721-001_closure_of_DEV-20260711-001.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Completed work", closure_doc)
        self.assertIn("ETHGOV-001", closure_doc)
        self.assertIn("DEV-20260711-001", closure_doc)

    def test_repository_governance_includes_deviation_validation(self) -> None:
        errors = validate_repository_governance(self.repo_root)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_malformed_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "deviation_log.jsonl"
            log_path.write_text("{not json}\n", encoding="utf-8")
            entries, parse_errors = load_deviation_log(log_path)
            self.assertEqual(entries, [])
            self.assertEqual(len(parse_errors), 1)
            self.assertIn("malformed JSON", parse_errors[0])

    def test_missing_field(self) -> None:
        entry = _valid_entry()
        del entry["approval_basis"]
        errors = validate_deviation_entry(entry, repo_root=self.repo_root)
        self.assertTrue(any("approval_basis" in error for error in errors))

    def test_duplicate_id(self) -> None:
        entry = _valid_entry()
        errors = validate_deviation_log([entry, dict(entry)], repo_root=self.repo_root)
        self.assertTrue(any("duplicate deviation_id" in error for error in errors))

    def test_invalid_status(self) -> None:
        entry = _valid_entry()
        entry["status"] = "approved"
        errors = validate_deviation_entry(entry, repo_root=self.repo_root)
        self.assertTrue(any("status must be one of" in error for error in errors))

    def test_absolute_and_path_traversal_paths(self) -> None:
        entry = _valid_entry()
        entry["evidence"] = list(entry["evidence"])
        entry["evidence"][0] = "C:/secrets/evidence.md"
        errors = validate_deviation_entry(entry, repo_root=self.repo_root)
        self.assertTrue(any("repository-relative" in error for error in errors))

        entry = _valid_entry()
        entry["affected_artefacts"] = list(entry["affected_artefacts"])
        entry["affected_artefacts"][0] = "../outside.md"
        errors = validate_deviation_entry(entry, repo_root=self.repo_root)
        self.assertTrue(any("repository-relative" in error for error in errors))

    def test_accepted_entry_without_approver(self) -> None:
        entry = _valid_entry()
        entry["approver"] = "   "
        errors = validate_deviation_entry(entry, repo_root=self.repo_root)
        self.assertTrue(any("non-empty approver" in error for error in errors))

        entry = _valid_entry()
        entry["approval_basis"] = ""
        errors = validate_deviation_entry(entry, repo_root=self.repo_root)
        self.assertTrue(any("non-empty approval_basis" in error for error in errors))

    def test_missing_evidence_path(self) -> None:
        entry = _valid_entry()
        entry["evidence"] = list(entry["evidence"])
        entry["evidence"].append("docs/decisions/does_not_exist.md")
        errors = validate_deviation_entry(entry, repo_root=self.repo_root)
        self.assertTrue(any("does not exist" in error for error in errors))

    def test_attempted_ethics_gate_bypass(self) -> None:
        entry = _valid_entry()
        entry["summary"] = "Set collection_permitted: true and proceed with annotation."
        errors = validate_deviation_entry(entry, repo_root=self.repo_root)
        self.assertTrue(any("bypass the ethics gate" in error for error in errors))

        entry = _valid_entry()
        entry["collection_permitted"] = True
        errors = validate_deviation_entry(entry, repo_root=self.repo_root)
        self.assertTrue(any("collection_permitted must not be set to true" in error for error in errors))

    def test_unchanged_protocol_without_execution_order_exception(self) -> None:
        entry = _valid_entry()
        entry["change_type"] = "protocol_amendment"
        entry["protocol_version_after"] = "unchanged (execution-order exception only)"
        errors = validate_deviation_entry(entry, repo_root=self.repo_root)
        self.assertTrue(
            any("unchanged protocol_version_after requires" in error for error in errors)
        )


if __name__ == "__main__":
    unittest.main()
