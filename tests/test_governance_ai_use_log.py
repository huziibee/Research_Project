"""Tests for AI-use log governance validation."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.governance.ai_use import (
    AI_USE_CATEGORIES,
    load_ai_use_log,
    validate_ai_use_entry,
    validate_ai_use_log,
)
from ambiguity_manager.paths import ProjectPaths


class TestGovernanceAiUseLog(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.paths = ProjectPaths.from_repo_root()
        cls.log_path = cls.paths.root / "docs" / "governance" / "logs" / "generative_ai_use_log.jsonl"
        cls.entries = load_ai_use_log(cls.log_path)

    def test_log_exists_with_three_backfill_entries(self) -> None:
        self.assertTrue(self.log_path.is_file())
        self.assertEqual(len(self.entries), 3)
        self.assertTrue(all(entry["historical_backfill"] for entry in self.entries))

    def test_use_categories_is_non_empty_unique_list(self) -> None:
        for entry in self.entries:
            categories = entry["use_categories"]
            self.assertIsInstance(categories, list)
            self.assertGreater(len(categories), 0)
            self.assertEqual(len(categories), len(set(categories)))
            self.assertTrue(set(categories).issubset(AI_USE_CATEGORIES))

    def test_tools_list_includes_cursor_and_openai(self) -> None:
        providers = set()
        for entry in self.entries:
            for tool in entry["tools"]:
                providers.add(tool["provider"])
                self.assertIsNone(tool["model"])
                self.assertEqual(tool["model_status"], "not_recorded")
        self.assertIn("Cursor", providers)
        self.assertIn("OpenAI", providers)

    def test_reject_empty_use_categories(self) -> None:
        entry = dict(self.entries[0])
        entry["use_categories"] = []
        errors = validate_ai_use_entry(entry)
        self.assertTrue(any("use_categories" in e for e in errors))

    def test_reject_duplicate_use_categories(self) -> None:
        entry = dict(self.entries[0])
        entry["use_categories"] = ["planning", "planning"]
        errors = validate_ai_use_entry(entry)
        self.assertTrue(any("duplicate" in e for e in errors))

    def test_reject_unknown_use_category(self) -> None:
        entry = dict(self.entries[0])
        entry["use_categories"] = ["planning", "unknown_category"]
        errors = validate_ai_use_entry(entry)
        self.assertTrue(any("unknown" in e for e in errors))

    def test_duplicate_entry_id_rejected(self) -> None:
        duplicate = [self.entries[0], self.entries[0]]
        errors = validate_ai_use_log(duplicate)
        self.assertTrue(any("duplicate" in e for e in errors))

    def test_activity_period_and_recorded_at_distinct(self) -> None:
        for entry in self.entries:
            self.assertIn("activity_period", entry)
            self.assertIn("recorded_at", entry)
            self.assertIn("time_precision", entry)

    def test_log_path_not_under_outputs(self) -> None:
        rel = self.log_path.relative_to(self.paths.root).as_posix()
        self.assertTrue(rel.startswith("docs/governance/logs/"))
        self.assertFalse(rel.startswith("outputs/"))


if __name__ == "__main__":
    unittest.main()
