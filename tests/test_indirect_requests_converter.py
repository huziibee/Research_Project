"""Tests for the IndirectRequests canonical converter (T04)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ambiguity_manager.converters.indirect_requests import (
    AMBIGUOUS_TARGET,
    EXPECTED_ARROW_FIELDS,
    MAPPING_VERSION,
    IndirectRequestsConversionError,
    IndirectRequestsSchemaError,
    convert_dataset,
    convert_split,
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
    SplitStatus,
)

FIXTURES = Path(__file__).parent / "fixtures" / "indirect_requests"


class IndirectRequestsConverterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "build_indirect_requests_fixtures",
            FIXTURES / "build_fixtures.py",
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.build()

    def _records_by_id(self, result) -> dict[str, object]:
        return {record.id: record for record in result.records}

    def test_expected_arrow_schema_validation(self) -> None:
        bad = FIXTURES / "bad_schema.arrow"
        with self.assertRaises(IndirectRequestsSchemaError):
            convert_split(bad, "train")

    def test_parser_count_agreement(self) -> None:
        result = convert_dataset(FIXTURES)
        self.assertEqual(result.summary["source_rows_read"], 6)
        self.assertEqual(result.summary["rows_per_split"]["train"], 4)
        self.assertEqual(result.summary["rows_per_split"]["validation"], 1)
        self.assertEqual(result.summary["rows_per_split"]["test"], 1)

    def test_float32_mean_world_understanding_rejected(self) -> None:
        bad = FIXTURES / "bad_float32_schema.arrow"
        with self.assertRaises(IndirectRequestsSchemaError):
            convert_split(bad, "train")

    def test_split_preservation_and_status_mapping(self) -> None:
        result = convert_dataset(FIXTURES)
        by_id = self._records_by_id(result)
        train = by_id["indirect_requests:train:0"]
        validation = by_id["indirect_requests:validation:0"]
        self.assertEqual(train.original_split, "train")
        self.assertEqual(train.split_status, SplitStatus.TRAIN)
        self.assertEqual(validation.original_split, "validation")
        self.assertEqual(validation.split_status, SplitStatus.DEV)

    def test_deterministic_source_ids(self) -> None:
        result = convert_dataset(FIXTURES)
        by_id = self._records_by_id(result)
        self.assertEqual(by_id["indirect_requests:train:0"].source_id, "train:0")
        self.assertEqual(by_id["indirect_requests:train:1"].source_id, "train:1")

    def test_concrete_row_conversion(self) -> None:
        result = convert_dataset(FIXTURES)
        rec = self._records_by_id(result)["indirect_requests:train:0"]
        self.assertEqual(rec.command, "I feel like something spicy tonight.")
        self.assertEqual(rec.scene_context, "User is choosing a restaurant.")
        self.assertIsNone(rec.capability_context)
        self.assertIsNone(rec.group_id)
        self.assertIsNone(rec.resolved_interpretation)
        self.assertFalse(rec.ambiguity_present)
        self.assertEqual(rec.ambiguity_types, [])
        self.assertIsNone(rec.primary_ambiguity_type)
        self.assertEqual(rec.compound_ambiguity_count, 0)
        self.assertEqual(rec.missing_slots, [])
        self.assertEqual(
            rec.slots,
            {"Cuisine of food served in the restaurant": "Mexican"},
        )
        self.assertTrue(rec.label_eligibility.intent_slots)
        self.assertFalse(rec.label_eligibility.ambiguity)

    def test_ambiguous_row_conversion(self) -> None:
        result = convert_dataset(FIXTURES)
        rec = self._records_by_id(result)["indirect_requests:train:1"]
        self.assertTrue(rec.ambiguity_present)
        self.assertEqual(rec.ambiguity_types, [AmbiguityType.PRAGMATIC])
        self.assertEqual(rec.primary_ambiguity_type, AmbiguityType.PRAGMATIC)
        self.assertEqual(rec.compound_ambiguity_count, 1)
        self.assertEqual(rec.missing_slots, ["Category to which the attraction belongs"])
        self.assertEqual(rec.slots, {})
        self.assertFalse(rec.label_eligibility.intent_slots)
        self.assertTrue(rec.label_eligibility.ambiguity)

    def test_unseen_concrete_target_converts(self) -> None:
        result = convert_dataset(FIXTURES)
        rec = self._records_by_id(result)["indirect_requests:validation:0"]
        self.assertEqual(rec.slots["Cuisine of food served in the restaurant"], "NeverSeenCuisine")
        self.assertFalse(rec.ambiguity_present)
        self.assertTrue(rec.label_eligibility.intent_slots)

    def test_missing_utterance_quarantined(self) -> None:
        result = convert_dataset(FIXTURES)
        reasons = {entry["reason"] for entry in result.quarantine}
        self.assertIn("missing_command", reasons)
        self.assertEqual(result.summary["rows_per_split"]["test"], 1)
        self.assertEqual(result.summary["rows_quarantined"], 2)

    def test_missing_slot_description_quarantined(self) -> None:
        result = convert_dataset(FIXTURES)
        slot_entries = [e for e in result.quarantine if e["reason"] == "missing_slot_description"]
        self.assertEqual(len(slot_entries), 1)
        self.assertEqual(slot_entries[0]["source_id"], "train:3")
        self.assertEqual(slot_entries[0]["source_row"]["target_slot_value"], "moderate")

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "build_indirect_requests_fixtures",
            FIXTURES / "build_fixtures.py",
        )
        assert spec and spec.loader
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        ambiguous_root = FIXTURES / "missing_slot_ambiguous"
        builder.write_ipc_stream(
            ambiguous_root / "train" / "data-00000-of-00001.arrow",
            [
                {
                    "creation_date": "2023-07-26T09:00:00.000000",
                    "utterance": "Ambiguous without slot description.",
                    "slot_description": "",
                    "situation": "Synthetic ambiguous quarantine case.",
                    "service": "Travel_1",
                    "possible_slot_values": "['A', 'B']",
                    "bool_rephrased_slot_values": "['A', 'B']",
                    "target_slot_value": "<ambiguous>",
                    "mean_world_understanding": 5.0,
                }
            ],
        )
        builder.write_ipc_stream(ambiguous_root / "validation" / "data-00000-of-00001.arrow", [])
        builder.write_ipc_stream(ambiguous_root / "test" / "data-00000-of-00001.arrow", [])
        ambiguous_result = convert_dataset(ambiguous_root)
        self.assertEqual(len(ambiguous_result.records), 0)
        self.assertEqual(len(ambiguous_result.quarantine), 1)
        self.assertEqual(ambiguous_result.quarantine[0]["reason"], "missing_slot_description")

    def test_record_level_confidence_and_status(self) -> None:
        result = convert_dataset(FIXTURES)
        for record in result.records:
            self.assertEqual(record.annotation_status, AnnotationStatus.WEAK_MAPPED)
            self.assertEqual(record.label_confidence, LabelConfidence.WEAK_DERIVED)
            self.assertEqual(record.record_class, RecordClass.SOURCE_CONVERTED)

    def test_no_fabricated_route_risk_capability(self) -> None:
        result = convert_dataset(FIXTURES)
        for record in result.records:
            self.assertIsNone(record.risk_level)
            self.assertIsNone(record.capability_status)
            self.assertIsNone(record.recommended_strategy)
            self.assertEqual(record.strategy_sequence, [])
            self.assertFalse(record.risk_relevant)
            self.assertFalse(record.compound_ambiguity)
            self.assertEqual(record.candidate_interpretations, [])

    def test_list_like_fields_preserved_as_strings(self) -> None:
        result = convert_dataset(FIXTURES)
        rec = self._records_by_id(result)["indirect_requests:train:0"]
        meta = rec.source_metadata
        self.assertEqual(set(meta.keys()), set(EXPECTED_ARROW_FIELDS))
        self.assertIsInstance(meta["possible_slot_values"], str)
        self.assertIsInstance(meta["bool_rephrased_slot_values"], str)
        self.assertEqual(meta["service"], "Restaurants_1")
        self.assertEqual(meta["creation_date"], "2023-07-26T00:55:08.699000")
        self.assertEqual(rec.slots["Cuisine of food served in the restaurant"], "Mexican")

    def test_canonical_schema_validation(self) -> None:
        result = convert_dataset(FIXTURES)
        for record in result.records:
            validate_canonical_record(record)

    def test_deterministic_ordering(self) -> None:
        first = [record.id for record in convert_dataset(FIXTURES).records]
        second = [record.id for record in convert_dataset(FIXTURES).records]
        self.assertEqual(
            first,
            [
                "indirect_requests:train:0",
                "indirect_requests:train:1",
                "indirect_requests:train:2",
                "indirect_requests:validation:0",
            ],
        )
        self.assertEqual(first, second)

    def test_duplicate_output_id_detection(self) -> None:
        from unittest.mock import patch

        from ambiguity_manager.converters.indirect_requests import ConversionResult, convert_split

        base = convert_split(FIXTURES / "train" / "data-00000-of-00001.arrow", "train")
        duplicate = ConversionResult(
            records=[base.records[0], base.records[0]],
            quarantine=[],
            summary=base.summary,
        )
        empty_summary = {
            "source_rows_read": 0,
            "rows_converted": 0,
            "rows_skipped": 0,
            "rows_quarantined": 0,
            "rows_ambiguous": 0,
            "rows_concrete_target": 0,
            "skip_reasons": {},
            "quarantine_reasons": {},
        }
        empty = ConversionResult(records=[], quarantine=[], summary=empty_summary)

        def fake_convert(path: Path, split: str) -> ConversionResult:
            if split == "train":
                return duplicate
            return empty

        with patch(
            "ambiguity_manager.converters.indirect_requests.convert_split",
            side_effect=fake_convert,
        ):
            with self.assertRaises(IndirectRequestsConversionError):
                convert_dataset(FIXTURES)

    def test_row_accounting_equality(self) -> None:
        result = convert_dataset(FIXTURES)
        summary = result.summary
        self.assertEqual(
            summary["source_rows_read"],
            summary["rows_converted"] + summary["rows_skipped"] + summary["rows_quarantined"],
        )
        self.assertEqual(summary["rows_converted"], len(result.records))
        self.assertEqual(summary["output_ids_unique"], len(result.records))
        self.assertEqual(
            summary["rows_ambiguous"] + summary["rows_concrete_target"],
            summary["rows_converted"],
        )

    def test_guarded_output_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            out = tmp_path / "indirect_requests_canonical.jsonl"
            quar = tmp_path / "indirect_requests_quarantine.jsonl"
            summ = tmp_path / "indirect_requests_conversion_summary.json"
            summary = run_conversion(FIXTURES, out, quar, summ)
            self.assertTrue(out.exists())
            self.assertTrue(quar.exists())
            self.assertTrue(summ.exists())
            self.assertEqual(summary["rows_converted"], 4)

    def test_raw_path_write_rejection(self) -> None:
        paths = ProjectPaths.from_repo_root()
        raw_target = paths.data_raw / "IndirectRequests" / "should_not_write.jsonl"
        quar = paths.data_interim / "indirect_requests" / "q.jsonl"
        summ = paths.outputs / "metrics" / "ir_summary.json"
        with self.assertRaises(RawDataWriteError):
            run_conversion(FIXTURES, raw_target, quar, summ)

    def test_summary_paths_are_repo_relative(self) -> None:
        paths = ProjectPaths.from_repo_root()
        out = paths.data_interim / "indirect_requests" / "_test_paths_canonical.jsonl"
        quar = paths.data_interim / "indirect_requests" / "_test_paths_quarantine.jsonl"
        summ = paths.outputs / "metrics" / "_test_paths_summary.json"
        try:
            summary = run_conversion(FIXTURES, out, quar, summ)
            for key in ("output_path", "quarantine_path", "summary_path"):
                value = summary[key]
                self.assertNotIn("\\", value)
                self.assertFalse(Path(value).is_absolute())
        finally:
            for path in (out, quar, summ):
                if path.exists():
                    path.unlink()

    def test_pyarrow_missing_raises(self) -> None:
        with mock.patch("ambiguity_manager.converters.indirect_requests._pyarrow_available", return_value=False):
            with self.assertRaises(ImportError):
                convert_split(FIXTURES / "train" / "data-00000-of-00001.arrow", "train")

    def test_ambiguous_sentinel_constant(self) -> None:
        self.assertEqual(AMBIGUOUS_TARGET, "<ambiguous>")
        self.assertEqual(MAPPING_VERSION, "indirect_requests-1.0.0")


if __name__ == "__main__":
    unittest.main()
