"""Tests for the ClariQ auxiliary canonical converter (T08)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ambiguity_manager.converters.clariq import (
    EXCLUDE_REASON,
    EXPECTED_HEADER,
    MAPPING_VERSION,
    ClariqConsistencyError,
    ClariqConversionError,
    ClariqHeaderError,
    convert_file,
    full_row_sha256,
    run_conversion,
    source_id_for_row,
)
from ambiguity_manager.io_guard import RawDataWriteError
from ambiguity_manager.paths import ProjectPaths, repo_relative_path
from ambiguity_manager.schema import validate_canonical_record
from ambiguity_manager.schema.taxonomies import (
    AnnotationStatus,
    LabelConfidence,
    RecordClass,
    SplitStatus,
)

FIXTURES = Path(__file__).parent / "fixtures" / "clariq"


class ClariqConverterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tiny = FIXTURES / "tiny_clariq.tsv"
        self.bad_header = FIXTURES / "bad_header_clariq.tsv"
        self.exact_duplicate = FIXTURES / "exact_duplicate_clariq.tsv"
        self.conflicting_composite = FIXTURES / "conflicting_composite_clariq.tsv"
        self.q00001 = FIXTURES / "q00001_clariq.tsv"
        self.duplicate_q00001 = FIXTURES / "duplicate_q00001_clariq.tsv"
        self.inconsistent_cn = FIXTURES / "inconsistent_cn_clariq.tsv"
        self.invalid_ids = FIXTURES / "invalid_ids_clariq.tsv"
        self.malformed_width_cn = FIXTURES / "malformed_width_cn_clariq.tsv"
        self.reorder_a = FIXTURES / "reorder_clariq_a.tsv"
        self.reorder_b = FIXTURES / "reorder_clariq_b.tsv"
        self.whitespace_trim = FIXTURES / "whitespace_trim_clariq.tsv"

    def test_module_import(self) -> None:
        self.assertEqual(EXPECTED_HEADER[0], "topic_id")

    def test_bad_header_raises(self) -> None:
        with self.assertRaises(ClariqHeaderError):
            convert_file(self.bad_header)

    def test_tiny_fixture_accounting(self) -> None:
        result = convert_file(self.tiny)
        self.assertEqual(result.summary["source_rows_read"], 2)
        self.assertEqual(result.summary["rows_converted"], 2)
        self.assertEqual(result.summary["rows_quarantined"], 0)
        self.assertEqual(result.summary["rows_excluded_by_policy"], 0)
        self.assertEqual(result.summary["rows_skipped"], 0)
        self.assertEqual(
            result.summary["source_rows_read"],
            result.summary["rows_converted"]
            + result.summary["rows_quarantined"]
            + result.summary["rows_excluded_by_policy"]
            + result.summary["rows_skipped"],
        )

    def test_canonical_fields_on_converted_row(self) -> None:
        result = convert_file(self.tiny)
        record = result.records[0]
        self.assertEqual(record.record_class, RecordClass.SOURCE_CONVERTED)
        self.assertEqual(record.source_dataset, "clariq")
        self.assertEqual(record.original_split, "train")
        self.assertEqual(record.split_status, SplitStatus.UNSPLIT)
        self.assertEqual(record.annotation_status, AnnotationStatus.WEAK_MAPPED)
        self.assertEqual(record.label_confidence, LabelConfidence.WEAK_DERIVED)
        self.assertEqual(record.mapping_notes, "auxiliary_non_robotic_clarification")
        self.assertEqual(record.mapping_version, MAPPING_VERSION)
        self.assertIsNone(record.ambiguity_present)
        self.assertIsNone(record.recommended_strategy)
        self.assertTrue(record.label_eligibility.clarification_target)
        self.assertFalse(record.label_eligibility.clarification_decision)
        self.assertFalse(record.label_eligibility.routing)
        self.assertFalse(record.label_eligibility.ambiguity)

    def test_exact_duplicate_quarantined(self) -> None:
        result = convert_file(self.exact_duplicate)
        self.assertEqual(result.summary["source_rows_read"], 2)
        self.assertEqual(result.summary["rows_converted"], 1)
        self.assertEqual(result.summary["rows_quarantined"], 1)
        self.assertEqual(result.quarantine[0]["reason"], "duplicate_exact_row")
        self.assertEqual(result.summary["exact_duplicate_groups"], 1)
        self.assertEqual(result.summary["exact_duplicate_rows_beyond_first"], 1)

    def test_conflicting_composite_rows_both_convert(self) -> None:
        result = convert_file(self.conflicting_composite)
        self.assertEqual(result.summary["rows_converted"], 2)
        self.assertEqual(result.summary["rows_quarantined"], 0)
        self.assertEqual(result.summary["conflicting_composite_groups"], 1)
        self.assertEqual(result.summary["distinct_rows_in_conflicting_composite_groups"], 2)
        ids = {record.source_id for record in result.records}
        self.assertEqual(len(ids), 2)

    def test_q00001_excluded_not_canonical(self) -> None:
        result = convert_file(self.q00001)
        self.assertEqual(result.summary["rows_converted"], 1)
        self.assertEqual(result.summary["rows_excluded_by_policy"], 1)
        self.assertEqual(result.summary["raw_q00001_rows"], 1)
        self.assertEqual(result.summary["unique_q00001_rows_excluded"], 1)
        excluded = result.excluded[0]
        self.assertEqual(excluded["reason"], EXCLUDE_REASON)
        self.assertIn("topic_id", excluded["source_row"])

    def test_duplicate_q00001_precedence(self) -> None:
        result = convert_file(self.duplicate_q00001)
        self.assertEqual(result.summary["raw_q00001_rows"], 2)
        self.assertEqual(result.summary["unique_q00001_rows_excluded"], 1)
        self.assertEqual(result.summary["rows_excluded_by_policy"], 1)
        self.assertEqual(result.summary["rows_quarantined"], 1)
        self.assertEqual(result.quarantine[0]["reason"], "duplicate_exact_row")

    def test_full_row_hash_stable_across_reordering(self) -> None:
        result_a = convert_file(self.reorder_a)
        result_b = convert_file(self.reorder_b)
        ids_a = [record.source_id for record in result_a.records]
        ids_b = [record.source_id for record in result_b.records]
        self.assertEqual(ids_a, ids_b)
        self.assertEqual(result_a.summary["conflicting_composite_groups"], 1)
        self.assertEqual(result_b.summary["conflicting_composite_groups"], 1)

    def test_verbatim_metadata_vs_trimmed_canonical(self) -> None:
        result = convert_file(self.whitespace_trim)
        record = result.records[0]
        self.assertEqual(record.command, "padded request.")
        self.assertEqual(record.gold_clarification_question, "padded question?")
        meta = record.source_metadata or {}
        self.assertEqual(meta["initial_request"], "  padded request.  ")
        self.assertEqual(meta["question"], "  padded question?  ")

    def test_inconsistent_clarification_need_raises(self) -> None:
        with self.assertRaises(ClariqConsistencyError):
            convert_file(self.inconsistent_cn)

    def test_malformed_width_does_not_trigger_topic_consistency_error(self) -> None:
        result = convert_file(self.malformed_width_cn)
        self.assertEqual(result.summary["source_rows_read"], 2)
        self.assertEqual(result.summary["rows_converted"], 1)
        self.assertEqual(result.summary["rows_quarantined"], 1)
        self.assertEqual(result.quarantine[0]["reason"], "malformed_row")

    def test_invalid_rows_quarantined(self) -> None:
        result = convert_file(self.invalid_ids)
        self.assertEqual(result.summary["source_rows_read"], 3)
        self.assertGreater(result.summary["rows_quarantined"], 0)
        reasons = {entry["reason"] for entry in result.quarantine}
        self.assertTrue(
            reasons
            & {
                "invalid_topic_id",
                "invalid_facet_id",
                "invalid_question_id",
                "unknown_clarification_need",
                "missing_initial_request",
            }
        )

    def test_source_id_includes_full_row_hash(self) -> None:
        result = convert_file(self.tiny)
        record = result.records[0]
        row = {
            "topic_id": "1",
            "initial_request": "Tell me about Obama family tree.",
            "topic_desc": "Find information on President Barack Obama family history.",
            "clarification_need": "2",
            "facet_id": "F0001",
            "facet_desc": "Find the TIME magazine photo essay.",
            "question_id": "Q00384",
            "question": "are you interested in seeing barack obamas family",
            "answer": "yes am interested",
        }
        digest = full_row_sha256(row)
        expected = source_id_for_row(row, digest)
        self.assertEqual(record.source_id, expected)
        self.assertTrue(record.source_id.endswith(digest))

    def test_all_converted_records_validate(self) -> None:
        result = convert_file(self.tiny)
        for record in result.records:
            validate_canonical_record(record)

    def test_no_forbidden_files_opened(self) -> None:
        real_open = Path.open

        def tracking_open(self_path, *args, **kwargs):  # type: ignore[no-untyped-def]
            if "ClariQ" in str(self_path):
                forbidden = (
                    "question_bank.tsv",
                    "dev.tsv",
                    "test.tsv",
                    "test_with_labels.tsv",
                    "multi_turn",
                    ".qrel",
                )
                name = self_path.name
                if any(token in name for token in forbidden):
                    raise AssertionError(f"forbidden ClariQ file opened: {self_path}")
            return real_open(self_path, *args, **kwargs)

        with mock.patch.object(Path, "open", tracking_open):
            convert_file(self.tiny)

    def test_run_conversion_guarded_paths(self) -> None:
        paths = ProjectPaths.from_repo_root()
        source = paths.data_raw / "ClariQ" / "data" / "train.tsv"
        if not source.is_file():
            self.skipTest("train.tsv not available in data/raw")
        test_dir = paths.outputs / "metrics" / "_t08_test"
        test_dir.mkdir(parents=True, exist_ok=True)
        output = test_dir / "clariq_canonical.jsonl"
        quarantine = test_dir / "clariq_quarantine.jsonl"
        excluded = test_dir / "clariq_excluded.jsonl"
        summary = test_dir / "clariq_conversion_summary.json"
        try:
            summary_result = run_conversion(source, output, quarantine, excluded, summary)
            self.assertTrue(output.is_file())
            self.assertTrue(summary.is_file())
            self.assertEqual(summary_result["source_rows_read"], 9176)
            self.assertIn("data/raw/ClariQ/data/train.tsv", summary_result["source_path"])
            rel_summary = summary_result["summary_path"].replace("\\", "/")
            self.assertFalse(Path(rel_summary).is_absolute())
            self.assertTrue(rel_summary.startswith("outputs/"))
            self.assertTrue(summary_result["authoritative_file_only"])
        finally:
            for path in (output, quarantine, excluded, summary):
                path.unlink(missing_ok=True)

    def test_run_conversion_fixture_source_not_authoritative(self) -> None:
        paths = ProjectPaths.from_repo_root()
        test_dir = paths.outputs / "metrics" / "_t08_test"
        test_dir.mkdir(parents=True, exist_ok=True)
        output = test_dir / "fixture_canonical.jsonl"
        quarantine = test_dir / "fixture_quarantine.jsonl"
        excluded = test_dir / "fixture_excluded.jsonl"
        summary = test_dir / "fixture_summary.json"
        try:
            summary_result = run_conversion(self.tiny, output, quarantine, excluded, summary)
            self.assertFalse(summary_result["authoritative_file_only"])
        finally:
            for path in (output, quarantine, excluded, summary):
                path.unlink(missing_ok=True)

    def test_raw_write_rejected(self) -> None:
        paths = ProjectPaths.from_repo_root()
        bad = paths.data_raw / "clariq_out.jsonl"
        with self.assertRaises(RawDataWriteError):
            run_conversion(
                self.tiny,
                bad,
                paths.data_interim / "clariq" / "q.jsonl",
                paths.data_interim / "clariq" / "e.jsonl",
                paths.outputs / "metrics" / "s.json",
            )


if __name__ == "__main__":
    unittest.main()
