"""Tests for the AmbiK canonical converter (T03).

Uses the standard-library ``unittest`` framework with tiny synthetic fixtures.
No full raw dataset is read. Run with ``python -m unittest``.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ambiguity_manager.converters.ambik import (
    AMBIGUITY_TYPE_MAP,
    EXPECTED_HEADER,
    MAPPING_VERSION,
    AmbikConversionError,
    AmbikHeaderError,
    convert_file,
    run_conversion,
)
from ambiguity_manager.io_guard import RawDataWriteError
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema import validate_canonical_record
from ambiguity_manager.schema.taxonomies import (
    AmbiguityType,
    AnnotationStatus,
    LabelConfidence,
    RecordClass,
    RouteLabel,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ambik"


class AmbikConverterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tiny = FIXTURES / "tiny_ambik.csv"
        self.bad_header = FIXTURES / "bad_header_ambik.csv"
        self.unknown_type = FIXTURES / "unknown_type_ambik.csv"
        self.quarantine = FIXTURES / "quarantine_ambik.csv"
        self.dup_id = FIXTURES / "dup_id_ambik.csv"
        self.missing_resolved = FIXTURES / "missing_resolved_ambik.csv"

    def _records_by_source_id(self, result) -> dict[str, object]:
        return {r.source_id: r for r in result.records}

    def test_expected_header_validation(self) -> None:
        result = convert_file(self.tiny)
        self.assertEqual(len(result.records), 3)
        with self.assertRaises(AmbikHeaderError):
            convert_file(self.bad_header)

    def test_valid_row_conversion(self) -> None:
        result = convert_file(self.tiny)
        by_id = self._records_by_source_id(result)
        rec = by_id["1"]
        self.assertEqual(rec.id, "ambik:1")
        self.assertEqual(rec.record_class, RecordClass.SOURCE_CONVERTED)
        self.assertEqual(rec.source_dataset, "ambik")
        self.assertEqual(rec.command, "Bring the cup.")
        self.assertEqual(rec.scene_context, "a cup, a mug")
        self.assertEqual(rec.gold_clarification_question, "Which cup should I bring?")
        self.assertEqual(rec.resolved_interpretation, "Robot, bring the red cup.")
        self.assertTrue(rec.ambiguity_present)
        self.assertEqual(rec.group_id, "ambik:group:1")
        self.assertEqual(rec.mapping_version, MAPPING_VERSION)

    def test_record_level_confidence_and_status(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertEqual(rec.annotation_status, AnnotationStatus.WEAK_MAPPED)
            self.assertEqual(rec.label_confidence, LabelConfidence.WEAK_DERIVED)

    def test_label_eligibility_flags(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertTrue(rec.label_eligibility.ambiguity)
            self.assertTrue(rec.label_eligibility.clarification_target)
            self.assertFalse(rec.label_eligibility.routing)
            self.assertFalse(rec.label_eligibility.risk)
            self.assertFalse(rec.label_eligibility.capability)
            self.assertFalse(rec.label_eligibility.clarification_decision)
            self.assertFalse(rec.label_eligibility.intent_slots)

    def test_source_id_determinism(self) -> None:
        first = convert_file(self.tiny)
        second = convert_file(self.tiny)
        self.assertEqual(
            [r.id for r in first.records],
            [r.id for r in second.records],
        )
        for rec in first.records:
            self.assertEqual(rec.id, f"ambik:{rec.source_id}")

    def test_ambiguity_type_mapping(self) -> None:
        result = convert_file(self.tiny)
        by_id = self._records_by_source_id(result)
        self.assertEqual(by_id["1"].primary_ambiguity_type, AmbiguityType.PREFERENCE)
        self.assertEqual(by_id["2"].primary_ambiguity_type, AmbiguityType.COMMONSENSE)
        self.assertEqual(by_id["3"].primary_ambiguity_type, AmbiguityType.SAFETY_PRECONDITION)
        for rec in result.records:
            self.assertEqual(rec.ambiguity_types, [rec.primary_ambiguity_type])
            self.assertFalse(rec.compound_ambiguity)
            self.assertEqual(rec.compound_ambiguity_count, 1)
        self.assertEqual(
            AMBIGUITY_TYPE_MAP,
            {
                "preferences": AmbiguityType.PREFERENCE,
                "common_sense_knowledge": AmbiguityType.COMMONSENSE,
                "safety": AmbiguityType.SAFETY_PRECONDITION,
            },
        )

    def test_unknown_ambiguity_type_quarantined(self) -> None:
        result = convert_file(self.unknown_type)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(len(result.quarantine), 1)
        entry = result.quarantine[0]
        self.assertEqual(entry["reason"], "unknown_ambiguity_type")
        self.assertEqual(entry["source_id"], "2")

    def test_missing_command_quarantined(self) -> None:
        result = convert_file(self.quarantine)
        reasons = {e["reason"] for e in result.quarantine}
        self.assertIn("missing_command", reasons)
        for entry in result.quarantine:
            if entry["reason"] == "missing_command":
                self.assertEqual(entry["source_id"], "2")

    def test_empty_question_quarantined(self) -> None:
        result = convert_file(self.quarantine)
        reasons = {e["reason"] for e in result.quarantine}
        self.assertIn("missing_clarification_question", reasons)

    def test_missing_resolved_interpretation_quarantined(self) -> None:
        result = convert_file(self.missing_resolved)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(len(result.quarantine), 1)
        entry = result.quarantine[0]
        self.assertEqual(entry["reason"], "missing_resolved_interpretation")
        self.assertEqual(entry["source_id"], "2")

    def test_list_like_fields_preserved_as_strings(self) -> None:
        """Correction #4: list-like source fields kept as raw strings, no eval-style parsing."""
        result = convert_file(self.tiny)
        by_id = self._records_by_source_id(result)
        rec = by_id["1"]
        meta = rec.source_metadata
        for field in ("variants", "amb_shortlist", "user_intent", "plan_for_clear_task", "plan_for_amb_task"):
            self.assertIsInstance(meta[field], str)
        # multi-line variants preserved verbatim, not split into a list
        self.assertIn("\n", meta["variants"])
        self.assertEqual(meta["variants"], "red cup\nblue cup")
        self.assertEqual(meta["amb_shortlist"], "red cup, blue cup")
        # canonical structured fields are not populated from these strings
        self.assertEqual(rec.slots, {})
        self.assertEqual(rec.missing_slots, [])
        self.assertIsNone(rec.intent)

    def test_canonical_schema_validation(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            validate_canonical_record(rec)

    def test_no_fabricated_risk_capability_route(self) -> None:
        result = convert_file(self.tiny)
        by_id = self._records_by_source_id(result)
        for rec in result.records:
            self.assertIsNone(rec.risk_level)
            self.assertIsNone(rec.capability_status)
            self.assertIsNone(rec.recommended_strategy)
            self.assertEqual(rec.strategy_sequence, [])
        self.assertFalse(by_id["1"].risk_relevant)
        self.assertFalse(by_id["2"].risk_relevant)
        self.assertTrue(by_id["3"].risk_relevant)

    def test_provenance_preserved_all_15_fields(self) -> None:
        result = convert_file(self.tiny)
        by_id = self._records_by_source_id(result)
        rec = by_id["1"]
        self.assertEqual(set(rec.source_metadata.keys()), set(EXPECTED_HEADER))
        self.assertEqual(rec.source_metadata["id"], "1")
        self.assertEqual(rec.source_metadata["ambiguity_type"], "preferences")
        self.assertEqual(rec.source_metadata["take_amb"], "")
        self.assertEqual(rec.source_license, "unresolved")

    def test_deterministic_jsonl_ordering(self) -> None:
        result = convert_file(self.quarantine)
        source_ids = [r.source_id for r in result.records]
        self.assertEqual(source_ids, sorted(source_ids, key=lambda x: int(x)))

    def test_duplicate_output_id_detection(self) -> None:
        with self.assertRaises(AmbikConversionError):
            convert_file(self.dup_id)

    def test_row_accounting_equality(self) -> None:
        result = convert_file(self.quarantine)
        s = result.summary
        self.assertEqual(
            s["source_rows_read"],
            s["rows_converted"] + s["rows_skipped"] + s["rows_quarantined"],
        )
        self.assertEqual(s["rows_converted"], len(result.records))
        self.assertEqual(s["rows_quarantined"], len(result.quarantine))
        self.assertEqual(s["output_ids_unique"], len(result.records))

    def test_guarded_output_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            out = tmp_path / "ambik_canonical.jsonl"
            quar = tmp_path / "ambik_quarantine.jsonl"
            summ = tmp_path / "ambik_conversion_summary.json"
            summary = run_conversion(self.quarantine, out, quar, summ)
            self.assertTrue(out.exists())
            self.assertTrue(quar.exists())
            self.assertTrue(summ.exists())
            self.assertEqual(summary["rows_converted"], out.read_text(encoding="utf-8").strip().count("\n") + 1)

    def test_raw_path_write_rejection(self) -> None:
        paths = ProjectPaths.from_repo_root()
        raw_target = paths.data_raw / "ambik" / "should_not_write.jsonl"
        quar = paths.data_interim / "ambik" / "q.jsonl"
        summ = paths.outputs / "metrics" / "s.json"
        with self.assertRaises(RawDataWriteError):
            run_conversion(self.tiny, raw_target, quar, summ)

    def test_conversion_summary_determinism(self) -> None:
        first = convert_file(self.tiny).summary
        second = convert_file(self.tiny).summary
        self.assertEqual(
            json.dumps(first, sort_keys=True),
            json.dumps(second, sort_keys=True),
        )

    def test_no_auxiliary_csv_usage(self) -> None:
        result = convert_file(self.tiny)
        self.assertFalse(result.summary["auxiliary_csvs_used"])
        # convert_file reads exactly the single primary path it is given
        self.assertEqual(result.summary["rows_converted"], 3)

    def test_summary_paths_are_repo_relative_with_forward_slashes(self) -> None:
        paths = ProjectPaths.from_repo_root()
        out = paths.data_interim / "ambik" / "_test_summary_paths_canonical.jsonl"
        quar = paths.data_interim / "ambik" / "_test_summary_paths_quarantine.jsonl"
        summ = paths.outputs / "metrics" / "_test_summary_paths_summary.json"
        try:
            summary = run_conversion(self.tiny, out, quar, summ)
            for key in ("source_path", "output_path", "quarantine_path", "summary_path"):
                value = summary[key]
                self.assertNotIn("\\", value)
                self.assertFalse(Path(value).is_absolute())
            self.assertEqual(
                summary["output_path"],
                "data/interim/ambik/_test_summary_paths_canonical.jsonl",
            )
            self.assertEqual(
                summary["quarantine_path"],
                "data/interim/ambik/_test_summary_paths_quarantine.jsonl",
            )
            self.assertEqual(
                summary["summary_path"],
                "outputs/metrics/_test_summary_paths_summary.json",
            )
            self.assertTrue(summary["source_path"].startswith("tests/fixtures/ambik/"))
        finally:
            for path in (out, quar, summ):
                if path.exists():
                    path.unlink()


if __name__ == "__main__":
    unittest.main()
