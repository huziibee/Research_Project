"""Tests for the CLARA/SaGC canonical converter (T07)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ambiguity_manager.converters.clara import (
    ALLOWED_TASKS,
    EXCLUDE_LABEL,
    MAPPING_VERSION,
    ClaraConversionError,
    ClaraJsonError,
    ClaraSchemaError,
    convert_file,
    normalize_source_id,
    run_conversion,
    serialize_scene,
)
from ambiguity_manager.io_guard import RawDataWriteError
from ambiguity_manager.paths import ProjectPaths, repo_relative_path
from ambiguity_manager.schema import validate_canonical_record
from ambiguity_manager.schema.taxonomies import (
    AnnotationStatus,
    CapabilityStatus,
    LabelConfidence,
    RecordClass,
    RouteLabel,
)

FIXTURES = Path(__file__).parent / "fixtures" / "clara"


class ClaraConverterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tiny = FIXTURES / "tiny_clara.json"
        self.invalid_source_id = FIXTURES / "invalid_source_id.json"
        self.missing_goal = FIXTURES / "missing_goal.json"
        self.unknown_label = FIXTURES / "unknown_label.json"
        self.unknown_task = FIXTURES / "unknown_task.json"
        self.duplicate_key = FIXTURES / "duplicate_top_level_key.json"
        self.whitespace_fields = FIXTURES / "whitespace_fields.json"
        self.boolean_label = FIXTURES / "boolean_label.json"
        self.non_string_goal = FIXTURES / "non_string_goal.json"
        self.non_string_scene_item = FIXTURES / "non_string_scene_item.json"
        self.extra_scene_key = FIXTURES / "extra_scene_key.json"
        self.missing_scene_key = FIXTURES / "missing_scene_key.json"
        self.leading_zero_id = FIXTURES / "leading_zero_id.json"
        self.normalized_duplicate_ids = FIXTURES / "normalized_duplicate_ids.json"
        self.negative_source_id = FIXTURES / "negative_source_id.json"
        self.whitespace_source_id = FIXTURES / "whitespace_source_id.json"

    def _records_by_source_id(self, result) -> dict[str, object]:
        return {record.source_id: record for record in result.records}

    def test_top_level_must_be_object(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            handle.write("[1, 2, 3]")
            bad_path = Path(handle.name)
        try:
            with self.assertRaises(ClaraSchemaError):
                convert_file(bad_path)
        finally:
            bad_path.unlink(missing_ok=True)

    def test_tiny_fixture_row_accounting(self) -> None:
        result = convert_file(self.tiny)
        self.assertEqual(result.summary["source_rows_read"], 4)
        self.assertEqual(result.summary["rows_converted"], 3)
        self.assertEqual(result.summary["rows_excluded_by_policy"], 1)
        self.assertEqual(result.summary["rows_quarantined"], 0)
        self.assertEqual(result.summary["rows_skipped"], 0)

    def test_label_0_mapping(self) -> None:
        result = convert_file(self.tiny)
        rec = self._records_by_source_id(result)["0"]
        self.assertFalse(rec.ambiguity_present)
        self.assertEqual(rec.ambiguity_types, [])
        self.assertIsNone(rec.primary_ambiguity_type)
        self.assertEqual(rec.capability_status, CapabilityStatus.CAPABLE)
        self.assertEqual(rec.recommended_strategy, RouteLabel.EXECUTE)
        self.assertTrue(rec.label_eligibility.routing)
        self.assertTrue(rec.label_eligibility.capability)
        self.assertTrue(rec.label_eligibility.ambiguity)
        self.assertTrue(rec.label_eligibility.clarification_decision)
        self.assertTrue(rec.label_eligibility.context_benefit)
        self.assertFalse(rec.label_eligibility.rejection)

    def test_label_1_mapping(self) -> None:
        result = convert_file(self.tiny)
        rec = self._records_by_source_id(result)["1"]
        self.assertTrue(rec.ambiguity_present)
        self.assertEqual(rec.ambiguity_types, [])
        self.assertIsNone(rec.primary_ambiguity_type)
        self.assertEqual(rec.capability_status, CapabilityStatus.CAPABLE)
        self.assertEqual(rec.recommended_strategy, RouteLabel.CLARIFY)
        self.assertTrue(rec.label_eligibility.routing)
        self.assertTrue(rec.label_eligibility.capability)

    def test_label_2_abstains_route_and_rejection(self) -> None:
        result = convert_file(self.tiny)
        rec = self._records_by_source_id(result)["2"]
        self.assertFalse(rec.ambiguity_present)
        self.assertEqual(rec.capability_status, CapabilityStatus.UNKNOWN)
        self.assertIsNone(rec.recommended_strategy)
        self.assertFalse(rec.label_eligibility.routing)
        self.assertFalse(rec.label_eligibility.capability)
        self.assertFalse(rec.label_eligibility.rejection)
        self.assertTrue(rec.label_eligibility.ambiguity)
        self.assertTrue(rec.label_eligibility.clarification_decision)

    def test_label_3_excluded_not_canonical(self) -> None:
        result = convert_file(self.tiny)
        self.assertEqual(len(result.excluded), 1)
        entry = result.excluded[0]
        self.assertEqual(entry["source_id"], "3")
        self.assertEqual(entry["raw_source_key"], "3")
        self.assertEqual(entry["reason"], "source_label_3_semantic_conflict")
        self.assertNotIn("3", self._records_by_source_id(result))

    def test_common_abstentions(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertFalse(rec.compound_ambiguity)
            self.assertEqual(rec.compound_ambiguity_count, 0)
            self.assertEqual(rec.missing_slots, [])
            self.assertFalse(rec.risk_relevant)
            self.assertIsNone(rec.risk_level)
            self.assertEqual(rec.strategy_sequence, [])
            self.assertIsNone(rec.gold_clarification_question)
            self.assertIsNone(rec.clarification_subtype)
            self.assertIsNone(rec.resolved_interpretation)
            self.assertIsNone(rec.intent)
            self.assertEqual(rec.slots, {})
            self.assertFalse(rec.label_eligibility.clarification_target)
            self.assertFalse(rec.label_eligibility.risk)
            self.assertFalse(rec.label_eligibility.intent_slots)
            self.assertFalse(rec.label_eligibility.compound_sequence)

    def test_record_level_status(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertEqual(rec.annotation_status, AnnotationStatus.WEAK_MAPPED)
            self.assertEqual(rec.label_confidence, LabelConfidence.WEAK_DERIVED)
            self.assertEqual(rec.record_class, RecordClass.SOURCE_CONVERTED)
            self.assertEqual(rec.source_dataset, "clara")
            self.assertEqual(rec.mapping_version, MAPPING_VERSION)

    def test_scene_context_is_deterministic_json(self) -> None:
        result = convert_file(self.tiny)
        rec = self._records_by_source_id(result)["0"]
        scene = rec.source_metadata["scene"]
        expected = serialize_scene(scene)
        self.assertEqual(rec.scene_context, expected)
        self.assertEqual(
            rec.scene_context,
            '{"floorplan":["kitchen","living room"],"objects":["water","bread"],"people":["person wearing blue shirt"]}',
        )

    def test_capability_context_robot_type_only(self) -> None:
        result = convert_file(self.tiny)
        by_id = self._records_by_source_id(result)
        self.assertEqual(by_id["0"].capability_context, "Robot type: cooking")
        self.assertEqual(by_id["1"].capability_context, "Robot type: cleaning")
        self.assertEqual(by_id["2"].capability_context, "Robot type: massaging")
        self.assertNotIn("grab", by_id["0"].capability_context or "")
        self.assertNotIn("action", (by_id["0"].capability_context or "").lower())

    def test_command_uses_trimmed_goal_metadata_preserves_raw(self) -> None:
        result = convert_file(self.whitespace_fields)
        rec = self._records_by_source_id(result)["0"]
        self.assertEqual(rec.command, "Prepare toast.")
        self.assertEqual(rec.source_metadata["goal"], "  Prepare toast.  ")
        self.assertEqual(rec.source_metadata["task"], "  cooking  ")
        self.assertEqual(rec.capability_context, "Robot type: cooking")

    def test_group_id_from_scene_hash(self) -> None:
        result = convert_file(self.tiny)
        rec = self._records_by_source_id(result)["0"]
        self.assertTrue(rec.group_id.startswith("clara:scene:"))

    def test_invalid_source_id_quarantined(self) -> None:
        result = convert_file(self.invalid_source_id)
        self.assertEqual(len(result.records), 0)
        self.assertEqual(len(result.quarantine), 1)
        self.assertEqual(result.quarantine[0]["reason"], "invalid_source_id")

    def test_missing_goal_quarantined(self) -> None:
        result = convert_file(self.missing_goal)
        self.assertEqual(len(result.records), 0)
        self.assertEqual(len(result.quarantine), 1)
        self.assertEqual(result.quarantine[0]["reason"], "missing_command")

    def test_unknown_label_quarantined(self) -> None:
        result = convert_file(self.unknown_label)
        self.assertEqual(len(result.quarantine), 1)
        self.assertEqual(result.quarantine[0]["reason"], "unknown_label")

    def test_unknown_task_quarantined(self) -> None:
        result = convert_file(self.unknown_task)
        self.assertEqual(len(result.quarantine), 1)
        self.assertEqual(result.quarantine[0]["reason"], "unknown_task")

    def test_duplicate_top_level_key_rejected(self) -> None:
        with self.assertRaises(ClaraJsonError):
            convert_file(self.duplicate_key)

    def test_deterministic_ordering(self) -> None:
        first = convert_file(self.tiny)
        second = convert_file(self.tiny)
        self.assertEqual([r.source_id for r in first.records], [r.source_id for r in second.records])
        self.assertEqual([r.source_id for r in first.records], ["0", "1", "2"])

    def test_canonical_schema_validation(self) -> None:
        result = convert_file(self.tiny)
        for record in result.records:
            validate_canonical_record(record)

    def test_allowed_tasks(self) -> None:
        self.assertEqual(ALLOWED_TASKS, frozenset({"cooking", "cleaning", "massaging"}))
        self.assertEqual(EXCLUDE_LABEL, 3)

    def test_accounting_invariant(self) -> None:
        result = convert_file(self.tiny)
        summary = result.summary
        total = (
            summary["rows_converted"]
            + summary["rows_quarantined"]
            + summary["rows_skipped"]
            + summary["rows_excluded_by_policy"]
        )
        self.assertEqual(summary["source_rows_read"], total)

    def test_run_conversion_guarded_writes(self) -> None:
        paths = ProjectPaths.from_repo_root()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output = tmp_path / "clara_canonical.jsonl"
            quarantine = tmp_path / "clara_quarantine.jsonl"
            excluded = tmp_path / "clara_excluded.jsonl"
            summary = tmp_path / "summary.json"
            run_conversion(self.tiny, output, quarantine, excluded, summary)
            self.assertTrue(output.is_file())
            self.assertTrue(excluded.is_file())
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["rows_converted"], 3)
            self.assertEqual(payload["rows_excluded_by_policy"], 1)

    def test_raw_write_rejected(self) -> None:
        paths = ProjectPaths.from_repo_root()
        raw_target = paths.data_raw / "CLARA-Dataset" / "data" / "blocked.jsonl"
        with self.assertRaises(RawDataWriteError):
            run_conversion(
                self.tiny,
                raw_target,
                paths.data_interim / "clara" / "q.jsonl",
                paths.data_interim / "clara" / "e.jsonl",
                paths.outputs / "metrics" / "blocked_summary.json",
            )

    def test_boolean_label_quarantined(self) -> None:
        result = convert_file(self.boolean_label)
        self.assertEqual(len(result.quarantine), 1)
        self.assertEqual(result.quarantine[0]["reason"], "unknown_label")

    def test_non_string_goal_quarantined(self) -> None:
        result = convert_file(self.non_string_goal)
        self.assertEqual(len(result.quarantine), 1)
        self.assertEqual(result.quarantine[0]["reason"], "non_string_goal")

    def test_non_string_scene_item_quarantined(self) -> None:
        result = convert_file(self.non_string_scene_item)
        self.assertEqual(len(result.quarantine), 1)
        self.assertEqual(result.quarantine[0]["reason"], "missing_scene")

    def test_extra_scene_key_quarantined(self) -> None:
        result = convert_file(self.extra_scene_key)
        self.assertEqual(len(result.quarantine), 1)
        self.assertEqual(result.quarantine[0]["reason"], "missing_scene")

    def test_missing_scene_key_quarantined(self) -> None:
        result = convert_file(self.missing_scene_key)
        self.assertEqual(len(result.quarantine), 1)
        self.assertEqual(result.quarantine[0]["reason"], "missing_scene")

    def test_leading_zero_source_id_quarantined(self) -> None:
        result = convert_file(self.leading_zero_id)
        self.assertEqual(len(result.quarantine), 1)
        self.assertEqual(result.quarantine[0]["reason"], "invalid_source_id")
        self.assertEqual(result.quarantine[0]["raw_source_key"], "01")

    def test_negative_source_id_quarantined(self) -> None:
        result = convert_file(self.negative_source_id)
        self.assertEqual(len(result.quarantine), 1)
        self.assertEqual(result.quarantine[0]["reason"], "invalid_source_id")

    def test_normalized_duplicate_source_ids_raise(self) -> None:
        with self.assertRaises(ClaraConversionError):
            convert_file(self.normalized_duplicate_ids)

    def test_whitespace_source_id_normalizes(self) -> None:
        result = convert_file(self.whitespace_source_id)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].source_id, "0")

    def test_normalize_source_id_rules(self) -> None:
        self.assertEqual(normalize_source_id("0"), "0")
        self.assertEqual(normalize_source_id(" 42 "), "42")
        self.assertIsNone(normalize_source_id("01"))
        self.assertIsNone(normalize_source_id("-1"))
        self.assertIsNone(normalize_source_id("abc"))

    def test_run_conversion_summary_path_in_summary_dict(self) -> None:
        paths = ProjectPaths.from_repo_root()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            summary_path = tmp_path / "summary.json"
            summary = run_conversion(
                self.tiny,
                tmp_path / "out.jsonl",
                tmp_path / "q.jsonl",
                tmp_path / "e.jsonl",
                summary_path,
            )
            self.assertEqual(summary["summary_path"], repo_relative_path(summary_path))


if __name__ == "__main__":
    unittest.main()
