"""Tests for the VAGUE canonical converter (T06)."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ambiguity_manager.converters.vague import (
    MAPPING_VERSION,
    PROJECTED_COLUMNS,
    VagueConversionError,
    VagueSchemaError,
    convert_file,
    parse_solution_triplet,
    run_conversion,
    validate_mcq_ordering,
    validate_parquet_schema,
)
from ambiguity_manager.io_guard import RawDataWriteError
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema import validate_canonical_record
from ambiguity_manager.schema.records import canonical_record_to_dict
from ambiguity_manager.schema.taxonomies import (
    AnnotationStatus,
    LabelConfidence,
    RecordClass,
    SplitStatus,
)

FIXTURES = Path(__file__).parent / "fixtures" / "vague"


def _build_fixtures() -> None:
    spec = importlib.util.spec_from_file_location(
        "build_vague_fixtures",
        FIXTURES / "build_fixtures.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.build()


class VagueConverterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _build_fixtures()

    def setUp(self) -> None:
        self.tiny = FIXTURES / "tiny_vague.parquet"
        self.bad_schema = FIXTURES / "bad_schema.parquet"
        self.quarantine = FIXTURES / "quarantine.parquet"
        self.missing_source_id = FIXTURES / "missing_source_id.parquet"
        self.dup_image_name = FIXTURES / "dup_image_name.parquet"
        self.with_image_column = FIXTURES / "with_image_column.parquet"
        self.bad_mcq_missing_1_correct = FIXTURES / "bad_mcq_missing_1_correct.parquet"
        self.bad_mcq_ordering_type = FIXTURES / "bad_mcq_ordering_type.parquet"
        self.bad_meta_missing_caption = FIXTURES / "bad_meta_missing_caption.parquet"
        self.bad_meta_rating_indirect_type = FIXTURES / "bad_meta_rating_indirect_type.parquet"
        self.ordering_valid_permutation = FIXTURES / "ordering_valid_permutation.parquet"
        self.ordering_quarantine = FIXTURES / "ordering_quarantine.parquet"

    def _records_by_id(self, result) -> dict[str, object]:
        return {record.id: record for record in result.records}

    def test_parse_solution_triplet_happy_path(self) -> None:
        slots, reason = parse_solution_triplet("(person1, hand over, binocular)")
        self.assertIsNone(reason)
        assert slots is not None
        self.assertEqual(slots["subject"], "person1")
        self.assertEqual(slots["action"], "hand over")
        self.assertEqual(slots["object"], "binocular")

    def test_parse_solution_triplet_without_parentheses(self) -> None:
        slots, reason = parse_solution_triplet("person2, adjust, strap")
        self.assertIsNone(reason)
        assert slots is not None
        self.assertEqual(slots["object"], "strap")

    def test_parse_solution_triplet_rejects_empty_component(self) -> None:
        slots, reason = parse_solution_triplet("(person1, , binocular)")
        self.assertIsNone(slots)
        self.assertEqual(reason, "invalid_solution_triplet")

    def test_parse_solution_triplet_rejects_wrong_part_count(self) -> None:
        slots, reason = parse_solution_triplet("(person1, only_two)")
        self.assertIsNone(slots)
        self.assertEqual(reason, "invalid_solution_triplet")

    def test_expected_schema_validation(self) -> None:
        with self.assertRaises(VagueSchemaError):
            convert_file(self.bad_schema)

    def test_schema_rejects_mcq_missing_1_correct(self) -> None:
        with self.assertRaises(VagueSchemaError) as ctx:
            convert_file(self.bad_mcq_missing_1_correct)
        self.assertIn("mcq.1_correct", str(ctx.exception))

    def test_schema_rejects_mcq_ordering_wrong_type(self) -> None:
        with self.assertRaises(VagueSchemaError) as ctx:
            convert_file(self.bad_mcq_ordering_type)
        self.assertIn("mcq.ordering", str(ctx.exception))

    def test_schema_rejects_meta_missing_caption(self) -> None:
        with self.assertRaises(VagueSchemaError) as ctx:
            convert_file(self.bad_meta_missing_caption)
        self.assertIn("meta.caption", str(ctx.exception))

    def test_schema_rejects_meta_rating_indirect_wrong_type(self) -> None:
        with self.assertRaises(VagueSchemaError) as ctx:
            convert_file(self.bad_meta_rating_indirect_type)
        self.assertIn("meta.rating.indirect", str(ctx.exception))

    def test_validate_mcq_ordering_accepts_permutation(self) -> None:
        self.assertIsNone(validate_mcq_ordering(["D", "C", "B", "A"]))

    def test_validate_mcq_ordering_rejects_missing(self) -> None:
        self.assertEqual(validate_mcq_ordering(None), "invalid_mcq_ordering")

    def test_validate_mcq_ordering_rejects_duplicate_letter(self) -> None:
        self.assertEqual(validate_mcq_ordering(["A", "A", "B", "C"]), "invalid_mcq_ordering")

    def test_validate_mcq_ordering_rejects_unknown_letter(self) -> None:
        self.assertEqual(validate_mcq_ordering(["A", "B", "C", "E"]), "invalid_mcq_ordering")

    def test_validate_mcq_ordering_rejects_wrong_length(self) -> None:
        self.assertEqual(validate_mcq_ordering(["A", "B", "C"]), "invalid_mcq_ordering")

    def test_valid_non_default_ordering_converts(self) -> None:
        result = convert_file(self.ordering_valid_permutation)
        self.assertEqual(result.summary["rows_converted"], 1)
        rec = result.records[0]
        self.assertEqual(rec.source_metadata["mcq"]["ordering"], ["D", "C", "B", "A"])
        self.assertEqual(
            rec.candidate_interpretations[0].text,
            "The speaker wants person1 to hand over the binocular to person2.",
        )

    def test_invalid_mcq_ordering_quarantine_cases(self) -> None:
        result = convert_file(self.ordering_quarantine)
        reasons = result.summary["quarantine_reasons"]
        self.assertEqual(result.summary["rows_converted"], 0)
        self.assertEqual(reasons.get("invalid_mcq_ordering"), 4)

    def test_parser_row_count_agreement(self) -> None:
        result = convert_file(self.tiny)
        self.assertEqual(result.summary["source_rows_read"], 3)
        self.assertEqual(
            result.summary["source_rows_read"],
            result.summary["rows_converted"]
            + result.summary["rows_quarantined"]
            + result.summary["rows_skipped"],
        )

    def test_ids_based_on_image_name(self) -> None:
        result = convert_file(self.tiny)
        rec = self._records_by_id(result)["vague:fixture_img_a@1"]
        self.assertEqual(rec.id, "vague:fixture_img_a@1")
        self.assertEqual(rec.source_id, "fixture_img_a@1")
        self.assertIsNone(rec.group_id)

    def test_command_and_scene_context_mapping(self) -> None:
        result = convert_file(self.tiny)
        rec = self._records_by_id(result)["vague:fixture_img_a@1"]
        self.assertEqual(rec.command, "Hey person1, why not share the view with person2?")
        self.assertEqual(rec.scene_context, "Three people outdoors; person1 holds binoculars.")
        self.assertEqual(rec.source_metadata["direct"], _row_direct_default())
        self.assertEqual(rec.intent, "(person1, hand over, binocular)")
        self.assertEqual(
            rec.resolved_interpretation,
            "The speaker wants person1 to hand over the binocular to person2.",
        )

    def test_ambiguity_and_routing_fields_abstain(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertIsNone(rec.ambiguity_present)
            self.assertEqual(rec.ambiguity_types, [])
            self.assertIsNone(rec.primary_ambiguity_type)
            self.assertFalse(rec.compound_ambiguity)
            self.assertEqual(rec.compound_ambiguity_count, 0)
            self.assertEqual(rec.missing_slots, [])
            self.assertIsNone(rec.recommended_strategy)
            self.assertEqual(rec.strategy_sequence, [])
            self.assertIsNone(rec.risk_level)
            self.assertIsNone(rec.capability_status)
            self.assertFalse(rec.label_eligibility.ambiguity)
            self.assertFalse(rec.label_eligibility.routing)
            self.assertFalse(rec.label_eligibility.risk)
            self.assertFalse(rec.label_eligibility.capability)

    def test_label_eligibility_intent_and_context_benefit(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertTrue(rec.label_eligibility.intent_slots)
            self.assertTrue(rec.label_eligibility.context_benefit)
            self.assertFalse(rec.label_eligibility.clarification_decision)
            self.assertFalse(rec.label_eligibility.clarification_target)

    def test_candidate_interpretations_structure(self) -> None:
        result = convert_file(self.tiny)
        rec = self._records_by_id(result)["vague:fixture_img_a@1"]
        self.assertEqual(len(rec.candidate_interpretations), 4)
        texts = [item.text for item in rec.candidate_interpretations]
        self.assertEqual(
            texts[0],
            "The speaker wants person1 to hand over the binocular to person2.",
        )
        self.assertEqual(texts[1], "The speaker wants person1 to share scrolls with friends.")
        self.assertEqual(texts[2], "The speaker wants person1 to act like a fortune teller.")
        self.assertEqual(texts[3], "The speaker wants person1 to hand over the telescope to person2.")
        for item in rec.candidate_interpretations:
            self.assertIsNone(item.confidence)
            self.assertIsNone(item.safety_status)

    def test_mcq_metadata_preserves_distractor_types_and_ordering(self) -> None:
        result = convert_file(self.tiny)
        rec = self._records_by_id(result)["vague:fixture_img_a@1"]
        mcq = rec.source_metadata["mcq"]
        self.assertIn("1_correct", mcq)
        self.assertIn("2_fake_scene", mcq)
        self.assertIn("3_surface_understanding", mcq)
        self.assertIn("4_wrong_entity", mcq)
        self.assertEqual(mcq["ordering"], ["A", "B", "C", "D"])

    def test_slots_parsed_from_solution(self) -> None:
        result = convert_file(self.tiny)
        rec = self._records_by_id(result)["vague:fixture_ego_001"]
        self.assertEqual(
            rec.slots,
            {"subject": "person2", "action": "adjust", "object": "strap"},
        )

    def test_split_fields(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertEqual(rec.original_split, "train")
            self.assertEqual(rec.split_status, SplitStatus.TRAIN)

    def test_record_classification(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertEqual(rec.record_class, RecordClass.SOURCE_CONVERTED)
            self.assertEqual(rec.annotation_status, AnnotationStatus.WEAK_MAPPED)
            self.assertEqual(rec.label_confidence, LabelConfidence.WEAK_DERIVED)
            self.assertEqual(rec.mapping_version, MAPPING_VERSION)

    def test_missing_source_id_quarantine(self) -> None:
        result = convert_file(self.missing_source_id)
        self.assertEqual(result.summary["quarantine_reasons"].get("missing_source_id"), 1)
        self.assertEqual(result.summary["rows_converted"], 1)

    def test_quarantine_reasons(self) -> None:
        result = convert_file(self.quarantine)
        reasons = result.summary["quarantine_reasons"]
        self.assertEqual(reasons.get("missing_command"), 1)
        self.assertEqual(reasons.get("invalid_solution_triplet"), 2)
        self.assertEqual(reasons.get("missing_scene_caption"), 1)

    def test_duplicate_image_name_raises_even_if_first_quarantined(self) -> None:
        with self.assertRaises(VagueConversionError):
            convert_file(self.dup_image_name)

    def test_no_derived_image_path(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            self.assertNotIn("image_path", rec.source_metadata)
            self.assertNotIn("image", rec.source_metadata)

    def test_image_column_excluded_from_projection(self) -> None:
        self.assertNotIn("image", PROJECTED_COLUMNS)

    def test_no_image_bytes_when_image_column_present(self) -> None:
        result = convert_file(self.with_image_column)
        self.assertEqual(result.summary["rows_converted"], 1)
        rec = result.records[0]
        self.assertNotIn("image", rec.source_metadata)
        self.assertNotIn("image_path", rec.source_metadata)
        dumped = json.dumps(canonical_record_to_dict(rec), default=str)
        self.assertNotIn("image_bytes", dumped)
        self.assertNotIn("\\xff", dumped)

    def test_pyarrow_unavailable_raises(self) -> None:
        with mock.patch("ambiguity_manager.converters.vague._pyarrow_available", return_value=False):
            with self.assertRaises(ImportError):
                convert_file(self.tiny)

    def test_canonical_validation_on_all_outputs(self) -> None:
        result = convert_file(self.tiny)
        for rec in result.records:
            validate_canonical_record(rec)

    def test_deterministic_ordering_by_row_index(self) -> None:
        result = convert_file(self.tiny)
        row_indices = [rec.source_metadata["row_index"] for rec in result.records]
        self.assertEqual(row_indices, sorted(row_indices))

    def test_subcorpus_counts(self) -> None:
        result = convert_file(self.tiny)
        counts = result.summary["rows_by_subcorpus"]
        self.assertEqual(counts.get("vcr"), 2)
        self.assertEqual(counts.get("ego4d"), 1)

    def test_raw_write_rejected(self) -> None:
        paths = ProjectPaths.from_repo_root()
        raw_target = paths.data_raw / "vague_bench" / "blocked.jsonl"
        with self.assertRaises(RawDataWriteError):
            run_conversion(
                self.tiny,
                raw_target,
                paths.data_interim / "vague" / "q.jsonl",
                paths.outputs / "metrics" / "vague_summary.json",
            )

    def test_run_conversion_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            out = tmp_path / "vague_canonical.jsonl"
            quarantine = tmp_path / "vague_quarantine.jsonl"
            summary = tmp_path / "vague_conversion_summary.json"
            summary_data = run_conversion(self.tiny, out, quarantine, summary)
            self.assertTrue(out.is_file())
            self.assertTrue(quarantine.is_file())
            self.assertTrue(summary.is_file())
            self.assertEqual(summary_data["rows_converted"], 3)
            self.assertEqual(summary_data["output_ids_unique"], 3)


def _row_direct_default() -> str:
    return "Hey, person1, please hand over the binocular to person2."


if __name__ == "__main__":
    unittest.main()
