"""Tests for JSON extraction and bounded deterministic repair."""

from __future__ import annotations

import unittest

from ambiguity_manager.model.parser import (
    MAX_REPAIR_OPERATIONS,
    MAX_REPAIR_ROUNDS,
    extract_and_repair_json,
)


class ModelParserTests(unittest.TestCase):
    def test_extract_from_markdown_fence(self) -> None:
        raw = 'Here is output:\n```json\n{"a": 1}\n```\n'
        result = extract_and_repair_json(raw)
        self.assertEqual(result.raw_output, raw)
        self.assertEqual(result.parsed_object, {"a": 1})
        self.assertGreaterEqual(result.repair_attempts, 1)

    def test_malformed_raw_output_retained(self) -> None:
        raw = "not json at all"
        result = extract_and_repair_json(raw)
        self.assertEqual(result.raw_output, raw)
        self.assertIsNone(result.parsed_object)

    def test_trailing_comma_repair(self) -> None:
        raw = '{"a": 1,}'
        result = extract_and_repair_json(raw)
        self.assertEqual(result.parsed_object, {"a": 1})

    def test_python_literal_normalisation(self) -> None:
        raw = '{"a": True, "b": None, "c": False}'
        result = extract_and_repair_json(raw)
        self.assertEqual(result.parsed_object, {"a": True, "b": None, "c": False})

    def test_repair_operation_count_bounded(self) -> None:
        raw = '```json\n{"x": 1,}\n``` extra {"y": 2}'
        result = extract_and_repair_json(raw)
        self.assertLessEqual(result.repair_attempts, MAX_REPAIR_OPERATIONS)
        self.assertLessEqual(len(result.repair_log), MAX_REPAIR_OPERATIONS)

    def test_semantic_rewriting_prohibited(self) -> None:
        raw = '{"risk_level": "invalid_enum_value"}'
        result = extract_and_repair_json(raw)
        self.assertEqual(result.parsed_object, {"risk_level": "invalid_enum_value"})

    def test_suffix_after_balanced_brace_removed(self) -> None:
        raw = '{"a": 1} trailing garbage'
        result = extract_and_repair_json(raw)
        self.assertEqual(result.parsed_object, {"a": 1})

    def test_max_rounds_constant(self) -> None:
        self.assertEqual(MAX_REPAIR_ROUNDS, 2)
        self.assertEqual(MAX_REPAIR_OPERATIONS, 6)


if __name__ == "__main__":
    unittest.main()
