"""CPU-only reference tests for T12 cluster architecture ADR and ticket contracts."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from ambiguity_manager.paths import ProjectPaths

REPO = ProjectPaths.from_repo_root().root

ADR_PATH = REPO / "docs" / "decisions" / "ADR_T12_cluster_inference_architecture.md"
NEW_TICKET_PATH = REPO / "cursor_plan" / "tickets" / "T12_cluster_model_stack_setup.md"
OLD_TICKET_PATH = REPO / "cursor_plan" / "tickets" / "T12_local_text_model_and_training_stack_setup.md"
HISTORICAL_README_PATH = REPO / "configs" / "model" / "evidence" / "historical" / "README.md"
LICENCE_REGISTER_PATH = REPO / "configs" / "licences" / "model_licence_register.json"

MODEL_ID = "Qwen/Qwen3-8B"
MODEL_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
CONTAINER_SHA = "d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1"
STAGE_LABELS = tuple(f"Stage {letter}" for letter in "ABCDEFGHI")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class T12ClusterAdrReferencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adr = _read(ADR_PATH)
        cls.new_ticket = _read(NEW_TICKET_PATH)
        cls.old_ticket = _read(OLD_TICKET_PATH)
        cls.historical_readme = _read(HISTORICAL_README_PATH)
        with LICENCE_REGISTER_PATH.open(encoding="utf-8") as handle:
            cls.licence_register = json.load(handle)

    def test_adr_exists(self) -> None:
        self.assertTrue(ADR_PATH.is_file())

    def test_new_ticket_exists(self) -> None:
        self.assertTrue(NEW_TICKET_PATH.is_file())

    def test_old_ticket_marked_superseded(self) -> None:
        top = "\n".join(self.old_ticket.splitlines()[:20])
        self.assertIn("SUPERSEDED", top)

    def test_old_ticket_references_replacement(self) -> None:
        self.assertIn("T12_cluster_model_stack_setup.md", self.old_ticket)
        self.assertIn("ADR_T12_cluster_inference_architecture.md", self.old_ticket)
        self.assertIn("archive/t12-local-wsl-slice4", self.old_ticket)

    def test_new_ticket_references_adr(self) -> None:
        self.assertIn("ADR_T12_cluster_inference_architecture.md", self.new_ticket)

    def test_qwen3_model_id_present(self) -> None:
        self.assertIn(MODEL_ID, self.adr)
        self.assertIn(MODEL_ID, self.new_ticket)

    def test_immutable_model_revision_exact(self) -> None:
        self.assertIn(MODEL_REVISION, self.adr)
        self.assertIn(MODEL_REVISION, self.new_ticket)
        self.assertEqual(self.adr.count(MODEL_REVISION), self.adr.count(MODEL_REVISION))

    def test_immutable_container_sha_exact(self) -> None:
        self.assertIn(CONTAINER_SHA, self.adr)
        self.assertIn(CONTAINER_SHA, self.new_ticket)

    def test_t11_remains_blocked(self) -> None:
        combined = self.adr + self.new_ticket
        self.assertRegex(combined, r"T11 remains\s+\*\*BLOCKED\*\*")
        self.assertNotIn("T11 passed", combined.lower())
        self.assertNotIn("T11: PASS", combined)

    def test_research_pool_prohibited(self) -> None:
        combined = self.adr + self.new_ticket
        self.assertIn("research-pool", combined.lower().replace("_", "-"))
        self.assertTrue(
            "prohibited" in combined.lower() or "no research pool" in combined.lower()
        )

    def test_stages_a_through_i_exist(self) -> None:
        for label in STAGE_LABELS:
            self.assertIn(label, self.new_ticket, msg=f"missing {label}")

    def test_stage_e_requires_ten_of_ten_schema_validity(self) -> None:
        stage_e = self._stage_section("E")
        self.assertIn("10/10", stage_e)
        self.assertIn("schema-valid", stage_e)

    def test_stage_f_requires_zero_optimiser_steps(self) -> None:
        stage_f = self._stage_section("F")
        self.assertIn("optimiser steps equal zero", stage_f.lower())

    def test_stage_g_includes_deterministic_synthetic_corpus(self) -> None:
        stage_g = self._stage_section("G")
        self.assertRegex(stage_g, r"100.?500")
        self.assertIn("deterministic", stage_g.lower())

    def test_stage_h_includes_github_release_publication(self) -> None:
        stage_h = self._stage_section("H")
        self.assertIn("GitHub", stage_h)
        self.assertIn("release", stage_h.lower())

    def test_stage_h_includes_email_notification(self) -> None:
        stage_h = self._stage_section("H")
        self.assertIn("email", stage_h.lower())

    def test_stage_h_uses_dependent_cpu_finaliser(self) -> None:
        stage_h = self._stage_section("H")
        self.assertIn("afterany", stage_h)
        self.assertIn("finaliser", stage_h.lower())

    def test_stage_i_contains_local_cleanup_gate(self) -> None:
        stage_i = self._stage_section("I")
        self.assertIn("cleanup gate", stage_i.lower())
        self.assertIn("eligible for deletion", stage_i.lower())

    def test_code_preservation_explicit(self) -> None:
        combined = self.adr + self.new_ticket + self.historical_readme
        self.assertIn("preserved", combined.lower())
        self.assertIn("Git history", combined)

    def test_immediate_local_model_deletion_prohibited(self) -> None:
        combined = self.adr + self.new_ticket
        self.assertIn("not deleted", combined.lower())
        self.assertIn("no automatic deletion", combined.lower())

    def test_selected_model_remains_null(self) -> None:
        self.assertIsNone(self.licence_register["selected_model"])

    def test_historical_readme_exists(self) -> None:
        self.assertTrue(HISTORICAL_README_PATH.is_file())
        self.assertIn("0/10", self.historical_readme)

    def _stage_section(self, letter: str) -> str:
        pattern = rf"## Stage {letter} —.*?(?=## Stage |\Z)"
        match = re.search(pattern, self.new_ticket, flags=re.DOTALL)
        self.assertIsNotNone(match, msg=f"Stage {letter} section not found")
        return match.group(0)


if __name__ == "__main__":
    unittest.main()
