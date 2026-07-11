"""Tests for T12 synthetic fixtures and silent-resolution integrity."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.model.integrity import (
    count_unsupported_commitments,
    load_synthetic_fixtures,
    validate_fixture_declarations,
)
from ambiguity_manager.paths import ProjectPaths

FIXTURES_PATH = (
    ProjectPaths.from_repo_root().root
    / "tests"
    / "fixtures"
    / "schema_v2"
    / "t12_synthetic_inputs.jsonl"
)


class T12SyntheticFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixtures = load_synthetic_fixtures(FIXTURES_PATH)

    def test_fixture_file_exists(self) -> None:
        self.assertTrue(FIXTURES_PATH.is_file())

    def test_ten_fixtures_loaded(self) -> None:
        self.assertEqual(len(self.fixtures), 10)

    def test_no_corpus_or_protected_paths(self) -> None:
        text = FIXTURES_PATH.read_text(encoding="utf-8").lower()
        for forbidden in (
            "data/interim",
            "data/processed",
            "weak_pool",
            "ambik:",
            "clara:",
            "protected",
        ):
            self.assertNotIn(forbidden, text)

    def test_support_declarations_validate(self) -> None:
        for fixture in self.fixtures:
            errors = validate_fixture_declarations(fixture)
            self.assertEqual(errors, [], msg=f"{fixture['fixture_id']}: {errors}")

    def test_silent_fixture_present(self) -> None:
        silent = [f for f in self.fixtures if f["fixture_id"] == "syn-003"]
        self.assertEqual(len(silent), 1)
        self.assertEqual(
            silent[0]["support_declarations"]["expected_route_pressure"],
            "silently_resolve",
        )

    def test_valid_silent_resolution_zero_unsupported(self) -> None:
        fixture = next(f for f in self.fixtures if f["fixture_id"] == "syn-003")
        prediction = {
            "recommended_strategy": "silently_resolve",
            "selected_interpretation": {
                "frame_id": "pred:syn-003:candidate:0",
                "supporting_evidence": [{"source": "scene_context", "span": "blue mug"}],
            },
            "unresolved_slots": [],
            "resolved_slots": [{"slot_name": "object", "value": "blue mug"}],
            "candidate_interpretations": [
                {"frame_id": "pred:syn-003:candidate:0", "text": "blue mug", "cpc": {}}
            ],
        }
        count = count_unsupported_commitments(fixture, prediction)
        self.assertEqual(count, 0)

    def test_invalid_silent_resolution_detected(self) -> None:
        fixture = next(f for f in self.fixtures if f["fixture_id"] == "syn-003")
        prediction = {
            "recommended_strategy": "silently_resolve",
            "selected_interpretation": {
                "frame_id": "pred:syn-003:candidate:0",
                "supporting_evidence": [{"source": "scene_context", "span": "red vase"}],
            },
            "unresolved_slots": ["object"],
            "resolved_slots": [{"slot_name": "object", "value": "red vase"}],
            "candidate_interpretations": [],
        }
        count = count_unsupported_commitments(fixture, prediction)
        self.assertGreater(count, 0)


if __name__ == "__main__":
    unittest.main()
