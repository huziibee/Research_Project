"""Tests for the CoDraw-iCR v2 canonical converter (T05)."""

from __future__ import annotations

import unittest
from pathlib import Path

from ambiguity_manager.converters.codraw_icr_v2 import (
    EXPECTED_HEADER,
    MAPPING_VERSION,
    CodrawIcrV2HeaderError,
    convert_file,
    normalize_mood,
    run_conversion,
)
from ambiguity_manager.io_guard import RawDataWriteError
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema import validate_canonical_record
from ambiguity_manager.schema.taxonomies import (
    AnnotationStatus,
    LabelConfidence,
    RecordClass,
    SplitStatus,
)

FIXTURES = Path(__file__).parent / "fixtures" / "codraw_icr_v2"


class CodrawIcrV2ConverterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tiny = FIXTURES / "tiny_codraw.tsv"
        self.bad_header = FIXTURES / "bad_header_codraw.tsv"
        self.malformed = FIXTURES / "malformed_codraw.tsv"
        self.anchor_edge = FIXTURES / "anchor_edge_codraw.tsv"
        self.quarantine = FIXTURES / "quarantine_codraw.tsv"
        self.dup_id = FIXTURES / "dup_id_codraw.tsv"
        self.non_icr = FIXTURES / "non_icr_codraw.tsv"
        self.unknown_mood = FIXTURES / "unknown_mood_codraw.tsv"

    def _records_by_id(self, result) -> dict[str, object]:
        return {record.id: record for record in result.records}

    def test_expected_header_validation(self) -> None:
        result = convert_file(self.tiny)
        self.assertEqual(len(result.records), 3)
        with self.assertRaises(CodrawIcrV2HeaderError):
            convert_file(self.bad_header)

    def test_parser_row_count_agreement(self) -> None:
        result = convert_file(self.tiny)
        self.assertEqual(result.summary["source_rows_read"], 3)
        self.assertEqual(
            result.summary["source_rows_read"],
            result.summary["rows_converted"] + result.summary["rows_quarantined"] + result.summary["rows_skipped"],
        )

    def test_malformed_row_quarantine(self) -> None:
        result = convert_file(self.malformed)
        self.assertEqual(result.summary["rows_converted"], 0)
        self.assertEqual(result.summary["quarantine_reasons"].get("malformed_row"), 1)

    def test_valid_row_conversion(self) -> None:
        result = convert_file(self.tiny)
        rec = self._records_by_id(result)["codraw_icr_v2:0"]
        self.assertEqual(rec.command, "put boy on slide")
        self.assertEqual(rec.gold_clarification_question, "is he on top ?")
        self.assertEqual(rec.source_dataset, "codraw_icr_v2")
        self.assertEqual(rec.source_id, "0")
        self.assertEqual(rec.group_id, "codraw_icr_v2:game:train_00001")

    def test_split_preservation(self) -> None:
        result = convert_file(self.tiny)
        by_id = self._records_by_id(result)
        self.assertEqual(by_id["codraw_icr_v2:0"].original_split, "train")
        self.assertEqual(by_id["codraw_icr_v2:0"].split_status, SplitStatus.TRAIN)
        self.assertEqual(by_id["codraw_icr_v2:1"].original_split, "validation")
        self.assertEqual(by_id["codraw_icr_v2:1"].split_status, SplitStatus.DEV)
        self.assertEqual(by_id["codraw_icr_v2:2"].original_split, "test")
        self.assertEqual(by_id["codraw_icr_v2:2"].split_status, SplitStatus.TEST)

    def test_ambiguity_fields_abstain(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertIsNone(rec.ambiguity_present)
            self.assertEqual(rec.ambiguity_types, [])
            self.assertIsNone(rec.primary_ambiguity_type)
            self.assertFalse(rec.compound_ambiguity)
            self.assertEqual(rec.compound_ambiguity_count, 0)
            self.assertEqual(rec.missing_slots, [])
            self.assertFalse(rec.label_eligibility.ambiguity)
            self.assertFalse(rec.label_eligibility.compound_sequence)

    def test_no_future_leakage_from_teller_after(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertNotIn("standing in front", rec.command)
            self.assertNotIn("kid on left", rec.command)
            self.assertNotIn("med plane", rec.command)
            for turn in rec.dialogue_history:
                self.assertNotIn("standing in front", turn)
                self.assertNotIn("kid on left", turn)
                self.assertNotIn("med plane", turn)
            self.assertIsNone(rec.resolved_interpretation)

    def test_source_instruction_unavailable_quarantine(self) -> None:
        result = convert_file(self.anchor_edge)
        self.assertEqual(result.summary["rows_converted"], 0)
        self.assertEqual(result.summary["quarantine_reasons"].get("source_instruction_unavailable"), 1)

    def test_missing_clarification_and_command_quarantine(self) -> None:
        result = convert_file(self.quarantine)
        reasons = result.summary["quarantine_reasons"]
        self.assertEqual(reasons.get("missing_clarification_utterance"), 1)
        self.assertEqual(reasons.get("missing_command"), 1)

    def test_duplicate_source_id_quarantine(self) -> None:
        result = convert_file(self.dup_id)
        self.assertEqual(result.summary["rows_converted"], 1)
        self.assertEqual(result.summary["quarantine_reasons"].get("duplicate_source_id"), 1)

    def test_unexpected_non_icr_row_quarantine(self) -> None:
        result = convert_file(self.non_icr)
        self.assertEqual(result.summary["quarantine_reasons"].get("unexpected_non_icr_row"), 1)

    def test_mood_normalization(self) -> None:
        self.assertEqual(normalize_mood("wh-question"), "wh- question")
        self.assertEqual(normalize_mood("wh-question, polar question"), "wh- question; polar question")
        self.assertEqual(normalize_mood("polar question, wh-question, polar question"), "polar question; wh- question")

    def test_unknown_mood_preserved_not_quarantined(self) -> None:
        result = convert_file(self.unknown_mood)
        self.assertEqual(result.summary["rows_converted"], 1)
        rec = result.records[0]
        self.assertEqual(rec.clarification_subtype, "custom mood label")
        self.assertGreaterEqual(result.summary.get("unknown_mood_token_warnings", 0), 1)

    def test_clarification_subtype_on_tiny_fixture(self) -> None:
        result = convert_file(self.tiny)
        by_id = self._records_by_id(result)
        self.assertEqual(by_id["codraw_icr_v2:0"].clarification_subtype, "polar question")
        self.assertEqual(by_id["codraw_icr_v2:2"].clarification_subtype, "wh- question; polar question")

    def test_label_eligibility_flags(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertTrue(rec.label_eligibility.clarification_target)
            self.assertFalse(rec.label_eligibility.clarification_decision)
            self.assertFalse(rec.label_eligibility.context_benefit)
            self.assertFalse(rec.label_eligibility.routing)
            self.assertFalse(rec.label_eligibility.risk)
            self.assertFalse(rec.label_eligibility.capability)
            self.assertFalse(rec.label_eligibility.intent_slots)
            self.assertFalse(rec.label_eligibility.rejection)

    def test_record_level_confidence_and_status(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertEqual(rec.annotation_status, AnnotationStatus.WEAK_MAPPED)
            self.assertEqual(rec.label_confidence, LabelConfidence.WEAK_DERIVED)
            self.assertIn("source-native", rec.mapping_notes or "")
            self.assertIn("weak-mapped", rec.mapping_notes or "")

    def test_no_fabricated_route_risk_capability(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertIsNone(rec.recommended_strategy)
            self.assertEqual(rec.strategy_sequence, [])
            self.assertFalse(rec.risk_relevant)
            self.assertIsNone(rec.risk_level)
            self.assertIsNone(rec.capability_status)

    def test_scene_context_null(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertIsNone(rec.scene_context)

    def test_source_metadata_preserves_content_flags(self) -> None:
        result = convert_file(self.tiny)
        meta = result.records[0].source_metadata or {}
        self.assertEqual(meta.get("position"), "0")
        self.assertEqual(meta.get("relation_to_other_cliparts"), "1")
        self.assertEqual(meta.get("clipart"), "two")
        self.assertEqual(meta.get("mood"), "polar question")

    def test_dialogue_history_empty(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertEqual(rec.dialogue_history, [])

    def test_canonical_schema_validation(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            validate_canonical_record(rec)

    def test_deterministic_ordering(self) -> None:
        result = convert_file(self.tiny)
        ids = [rec.source_id for rec in result.records]
        self.assertEqual(ids, sorted(ids, key=int))

    def test_mapping_version(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertEqual(rec.mapping_version, MAPPING_VERSION)

    def test_does_not_read_auxiliary_raw_path(self) -> None:
        raw_path = ProjectPaths.from_repo_root().data_raw / "codraw-icr-v2" / "codraw-icr-v2_raw.tsv"
        with self.assertRaises(CodrawIcrV2HeaderError):
            convert_file(raw_path)

    def test_guarded_writes_reject_raw_output(self) -> None:
        paths = ProjectPaths.from_repo_root()
        raw_out = paths.data_raw / "codraw-icr-v2" / "out.jsonl"
        with self.assertRaises(RawDataWriteError):
            run_conversion(
                self.tiny,
                raw_out,
                paths.data_interim / "codraw_icr_v2" / "q.jsonl",
                paths.outputs / "metrics" / "s.json",
            )

    def test_run_conversion_repo_relative_summary_paths(self) -> None:
        paths = ProjectPaths.from_repo_root()
        out = paths.data_interim / "codraw_icr_v2" / "_test_summary_paths_canonical.jsonl"
        quar = paths.data_interim / "codraw_icr_v2" / "_test_summary_paths_quarantine.jsonl"
        summ = paths.outputs / "metrics" / "_test_summary_paths_summary.json"
        try:
            summary_dict = run_conversion(self.tiny, out, quar, summ)
            for key in ("source_path", "output_path", "quarantine_path", "summary_path"):
                value = summary_dict[key]
                self.assertNotIn("\\", value)
                self.assertFalse(Path(value).is_absolute())
            self.assertEqual(
                summary_dict["output_path"],
                "data/interim/codraw_icr_v2/_test_summary_paths_canonical.jsonl",
            )
        finally:
            for path in (out, quar, summ):
                if path.exists():
                    path.unlink()

    def test_expected_header_constant(self) -> None:
        self.assertEqual(len(EXPECTED_HEADER), 26)
        self.assertEqual(EXPECTED_HEADER[0], "")
        self.assertEqual(EXPECTED_HEADER[1], "teller_before")


if __name__ == "__main__":
    unittest.main()
