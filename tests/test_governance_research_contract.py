"""Tests for research contract governance validation."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.governance.hashing import verify_contract_sidecar
from ambiguity_manager.governance.research_contract import (
    MANDATORY_SYSTEM_IDS,
    validate_research_contract,
)
from ambiguity_manager.paths import ProjectPaths


class TestGovernanceResearchContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.paths = ProjectPaths.from_repo_root()
        cls.contract_path = cls.paths.root / "configs" / "research" / "research_contract_v1.json"
        cls.sidecar_path = cls.paths.root / "configs" / "research" / "research_contract_v1.sha256"
        with cls.contract_path.open(encoding="utf-8") as handle:
            cls.contract = json.load(handle)

    def test_contract_file_exists(self) -> None:
        self.assertTrue(self.contract_path.is_file())
        self.assertTrue(self.sidecar_path.is_file())

    def test_sidecar_verifies(self) -> None:
        self.assertTrue(verify_contract_sidecar(self.contract_path, self.sidecar_path))

    def test_seven_mandatory_systems(self) -> None:
        systems = self.contract["mandatory_systems"]
        self.assertEqual(len(systems), 7)
        ids = [entry["id"] for entry in systems]
        self.assertEqual(ids, MANDATORY_SYSTEM_IDS)
        self.assertTrue(all(entry.get("optional") is False for entry in systems))

    def test_mandatory_finetuning(self) -> None:
        policy = self.contract["model_policy"]
        self.assertTrue(policy["mandatory_supervised_finetuning"])
        self.assertEqual(policy["finetuning_blocked_substitution"], "BLOCKED")

    def test_text_only_no_lvlm(self) -> None:
        scope = self.contract["scope"]
        self.assertTrue(scope["text_only"])
        self.assertFalse(scope["raw_image_lvlm"])

    def test_supersession_explicit(self) -> None:
        supersession = self.contract["supersession"]
        self.assertEqual(supersession["proposal_dataset_section"], "superseded")
        self.assertEqual(supersession["proposal_calendar_schedule"], "superseded")
        self.assertEqual(supersession["remaining_methodology"], "binding_unless_deviation")

    def test_primary_outcome_routing(self) -> None:
        self.assertEqual(self.contract["primary_outcome"], "routing_correctness")
        self.assertIn("intent_cpc_correctness", self.contract["supporting_outcomes"])

    def test_invalid_route_rejected(self) -> None:
        bad = dict(self.contract)
        bad["canonical_routes"] = self.contract["canonical_routes"] + ["invalid_route"]
        self.assertTrue(validate_research_contract(bad))

    def test_optional_system_rejected(self) -> None:
        bad = json.loads(json.dumps(self.contract))
        bad["mandatory_systems"][0]["optional"] = True
        errors = validate_research_contract(bad)
        self.assertTrue(any("optional" in e for e in errors))

    def test_eighth_system_rejected(self) -> None:
        bad = json.loads(json.dumps(self.contract))
        bad["mandatory_systems"].append({"id": "extra_system", "optional": False})
        errors = validate_research_contract(bad)
        self.assertTrue(any("seven" in e.lower() or "mandatory_systems" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
