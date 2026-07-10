"""Tests for dataset audit (T02)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ambiguity_manager.io_guard import RawDataWriteError
from ambiguity_manager.paths import ProjectPaths

FIXTURES = Path(__file__).parent / "fixtures" / "dataset_audit"


class AuditTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        (self.tmp_path / "pyproject.toml").write_text(
            "[project]\nname = 'tmp'\n", encoding="utf-8"
        )
        patcher = mock.patch(
            "ambiguity_manager.paths.repo_root",
            return_value=self.tmp_path.resolve(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.paths = ProjectPaths.from_repo_root()
        self.paths.ensure_project_dirs()

    def tearDown(self) -> None:
        self._tmp.cleanup()


class ConfigValidationTests(unittest.TestCase):
    def test_valid_inclusion_register_accepted(self) -> None:
        from ambiguity_manager.data_audit.config import load_inclusion_register, validate_inclusion_register

        data = load_inclusion_register(FIXTURES / "valid_register.json")
        errors = validate_inclusion_register(data)
        self.assertEqual(errors, [])

    def test_invalid_inclusion_register_rejected(self) -> None:
        from ambiguity_manager.data_audit.config import load_inclusion_register, validate_inclusion_register

        data = load_inclusion_register(FIXTURES / "invalid_register.json")
        errors = validate_inclusion_register(data)
        self.assertTrue(any("decision" in e for e in errors))

    def test_valid_licence_manifest_accepted(self) -> None:
        from ambiguity_manager.data_audit.config import load_licence_manifest, validate_licence_manifest

        data = load_licence_manifest(FIXTURES / "valid_licence_manifest.json")
        errors = validate_licence_manifest(data)
        self.assertEqual(errors, [])

    def test_licence_verified_without_evidence_rejected(self) -> None:
        from ambiguity_manager.data_audit.config import load_licence_manifest, validate_licence_manifest

        data = load_licence_manifest(FIXTURES / "invalid_licence_manifest.json")
        errors = validate_licence_manifest(data)
        self.assertTrue(any("evidence" in e.lower() or "verified" in e.lower() for e in errors))

    def test_licence_identifier_without_evidence_rejected(self) -> None:
        from ambiguity_manager.data_audit.config import load_licence_manifest, validate_licence_manifest

        data = load_licence_manifest(FIXTURES / "valid_licence_manifest.json")
        data["entries"][0]["licence_identifier"] = "Apache-2.0"
        errors = validate_licence_manifest(data)
        self.assertTrue(errors)


class ReaderTests(unittest.TestCase):
    def test_csv_row_count(self) -> None:
        from ambiguity_manager.data_audit.readers import read_csv_audit

        result = read_csv_audit(FIXTURES / "tiny.csv", critical_fields=["id", "name"])
        self.assertTrue(result.ok)
        self.assertEqual(result.record_count, 3)
        self.assertEqual(result.header_fields, ["id", "name"])

    def test_tsv_row_count(self) -> None:
        from ambiguity_manager.data_audit.readers import read_tsv_audit

        result = read_tsv_audit(FIXTURES / "tiny.tsv", critical_fields=["topic_id", "question_id"])
        self.assertTrue(result.ok)
        self.assertEqual(result.record_count, 2)

    def test_json_array_count(self) -> None:
        from ambiguity_manager.data_audit.readers import read_json_audit

        result = read_json_audit(FIXTURES / "tiny.json")
        self.assertTrue(result.ok)
        self.assertEqual(result.record_count, 3)

    def test_jsonl_count(self) -> None:
        from ambiguity_manager.data_audit.readers import read_jsonl_audit

        result = read_jsonl_audit(FIXTURES / "tiny.jsonl", critical_fields=["id"])
        self.assertTrue(result.ok)
        self.assertEqual(result.record_count, 3)

    def test_malformed_csv_detected(self) -> None:
        from ambiguity_manager.data_audit.readers import read_csv_audit

        result = read_csv_audit(FIXTURES / "malformed.csv", critical_fields=["id"])
        self.assertFalse(result.ok)
        self.assertEqual(result.error_kind, "inconsistent_row_width")

    def test_malformed_json_detected(self) -> None:
        from ambiguity_manager.data_audit.readers import read_json_audit

        result = read_json_audit(FIXTURES / "malformed.json")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_kind, "syntax_error")

    def test_inconsistent_tsv_width_detected(self) -> None:
        from ambiguity_manager.data_audit.readers import read_tsv_audit

        result = read_tsv_audit(FIXTURES / "inconsistent.tsv", critical_fields=["a"])
        self.assertFalse(result.ok)
        self.assertEqual(result.error_kind, "inconsistent_row_width")


class CheckTests(unittest.TestCase):
    def test_lfs_pointer_detected(self) -> None:
        from ambiguity_manager.data_audit.checks import is_lfs_pointer

        self.assertTrue(is_lfs_pointer(FIXTURES / "lfs_pointer.bin"))

    def test_duplicate_ids_detected(self) -> None:
        from ambiguity_manager.data_audit.checks import check_duplicate_ids_csv

        result = check_duplicate_ids_csv(FIXTURES / "dup_ids.csv", id_fields=["id"])
        self.assertTrue(result.performed)
        self.assertEqual(result.duplicate_count, 1)

    def test_split_overlap_warning(self) -> None:
        from ambiguity_manager.data_audit.checks import check_split_overlap_tsv

        result = check_split_overlap_tsv(
            [FIXTURES / "split_a.tsv", FIXTURES / "split_b.tsv"],
            id_fields=["question_id"],
        )
        self.assertTrue(result.performed)
        self.assertEqual(result.overlap_count, 1)
        self.assertEqual(result.status, "warning")

    def test_code_only_repo_detected(self) -> None:
        from ambiguity_manager.data_audit.checks import is_code_only_tree

        code_dir = FIXTURES / "code_only"
        code_dir.mkdir(exist_ok=True)
        (code_dir / "download_data.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        (code_dir / "pipeline.py").write_text("print('x')\n", encoding="utf-8")
        self.assertTrue(is_code_only_tree(code_dir))

    def test_metadata_only_detected(self) -> None:
        from ambiguity_manager.data_audit.checks import is_metadata_only_tree

        self.assertTrue(is_metadata_only_tree(FIXTURES / "metadata_only"))

    def test_classify_verified(self) -> None:
        from ambiguity_manager.data_audit.checks import classify_verification_status

        status = classify_verification_status(
            decision="include",
            excluded=False,
            blocked=False,
            payload_readable=True,
            metadata_only=False,
            has_warnings=False,
            needs_verification=False,
        )
        self.assertEqual(status, "verified")

    def test_classify_blocked(self) -> None:
        from ambiguity_manager.data_audit.checks import classify_verification_status

        status = classify_verification_status(
            decision="include",
            excluded=False,
            blocked=True,
            payload_readable=False,
            metadata_only=False,
            has_warnings=False,
            needs_verification=False,
        )
        self.assertEqual(status, "blocked")

    def test_classify_mapping_todo_verify(self) -> None:
        from ambiguity_manager.data_audit.checks import classify_mapping_verification_status

        status = classify_mapping_verification_status(
            [{"code": "TODO_VERIFY_LABEL_MAPPING", "field": "label", "note": "x"}]
        )
        self.assertEqual(status, "TODO_VERIFY")

    def test_classify_mapping_verified_when_no_risks(self) -> None:
        from ambiguity_manager.data_audit.checks import classify_mapping_verification_status

        self.assertEqual(classify_mapping_verification_status([]), "verified")

    def test_teach_tatc_like_code_only_tree_detected(self) -> None:
        from ambiguity_manager.data_audit.checks import is_code_only_tree

        with tempfile.TemporaryDirectory() as tmp:
            code_dir = Path(tmp) / "teach_tatc_like"
            code_dir.mkdir()
            (code_dir / "download_data.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            (code_dir / "pipeline.py").write_text("print('x')\n", encoding="utf-8")
            meta_dir = code_dir / "src" / "teach" / "meta_data_files" / "task_definitions"
            meta_dir.mkdir(parents=True)
            (meta_dir / "101__toast.json").write_text("{}\n", encoding="utf-8")
            replay_dir = code_dir / "experiments" / "testing" / "replay"
            replay_dir.mkdir(parents=True)
            (replay_dir / "file.json").write_text("{}\n", encoding="utf-8")
            self.assertTrue(is_code_only_tree(code_dir))

    def test_teach_tatc_excluded_audit_classification(self) -> None:
        from ambiguity_manager.data_audit.runner import audit_dataset_entry

        with tempfile.TemporaryDirectory() as tmp:
            code_dir = Path(tmp)
            raw_root = code_dir / "data" / "raw" / "teach_tatc"
            raw_root.mkdir(parents=True)
            (raw_root / "download_data.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            (raw_root / "pipeline.py").write_text("print('x')\n", encoding="utf-8")
            meta_dir = raw_root / "src" / "teach" / "meta_data_files"
            meta_dir.mkdir(parents=True)
            (meta_dir / "default_definitions.json").write_text("{}\n", encoding="utf-8")

            result = audit_dataset_entry(
                repo_root=code_dir,
                entry={
                    "dataset_id": "teach_tatc",
                    "display_name": "teach_tatc",
                    "decision": "exclude",
                    "role": "excluded",
                    "expected_converter_ticket": None,
                },
                spec={
                    "raw_root": "teach_tatc",
                    "entry_type": "git_submodule",
                    "split_structure": "none",
                    "mapping_risks": [],
                },
                licence_entry={"dataset_id": "teach_tatc", "licence_status": "stated_unverified"},
            )
            self.assertTrue(result["code_only"])
            self.assertEqual(result["payload_verification_status"], "excluded")

    def test_multi_component_authoritative_totals(self) -> None:
        from ambiguity_manager.data_audit.runner import audit_dataset_entry

        raw = Path(tempfile.mkdtemp()) / "repo"
        splits = {
            "train": "id\n1\n2\n",
            "validation": "id\n1\n",
            "test": "id\n1\n2\n3\n",
        }
        for split_name, content in splits.items():
            split_dir = raw / "data" / "raw" / "fixture_multi" / split_name
            split_dir.mkdir(parents=True)
            (split_dir / "data.csv").write_text(content, encoding="utf-8")

        result = audit_dataset_entry(
            repo_root=raw,
            entry={
                "dataset_id": "fixture_multi",
                "display_name": "Fixture Multi",
                "decision": "include",
                "role": "core",
                "expected_converter_ticket": "T99",
            },
            spec={
                "raw_root": "fixture_multi",
                "authoritative_components": [
                    {
                        "relative_path": f"fixture_multi/{name}/data.csv",
                        "file_type": "csv",
                        "critical_fields": ["id"],
                        "component_name": name,
                    }
                    for name in splits
                ],
                "mapping_risks": [{"code": "TODO_VERIFY_LABEL_MAPPING", "field": "id", "note": "test"}],
            },
            licence_entry={"dataset_id": "fixture_multi", "licence_status": "unresolved"},
        )
        self.assertEqual(result["total_authoritative_record_count"], 6)
        self.assertEqual(result["authoritative_component_counts"], {"train": 2, "validation": 1, "test": 3})
        self.assertEqual(result["payload_verification_status"], "verified")
        self.assertEqual(result["mapping_verification_status"], "TODO_VERIFY")


class WriterTests(AuditTestBase):
    def test_blocks_write_under_data_raw(self) -> None:
        from ambiguity_manager.data_audit.writer import write_audit_json

        with self.assertRaises(RawDataWriteError):
            write_audit_json({"audit_schema_version": "1.0.0"}, self.paths.data_raw / "x.json")

    def test_deterministic_json_output(self) -> None:
        from ambiguity_manager.data_audit.writer import dumps_audit_json

        payload = {"b": 1, "a": [{"z": 1, "y": 2}]}
        self.assertEqual(dumps_audit_json(payload), dumps_audit_json(payload))

    def test_no_absolute_paths_in_output(self) -> None:
        from ambiguity_manager.data_audit.writer import dumps_audit_json

        text = dumps_audit_json(
            {
                "datasets": [
                    {
                        "authoritative_files": [
                            {"relative_path": "AmbiK/AmbiK_data.csv"},
                        ]
                    }
                ]
            }
        )
        home = str(Path.home())
        if os.name == "nt":
            self.assertNotIn(home.lower(), text.lower())
        else:
            self.assertNotIn(home, text)


class RunnerTests(AuditTestBase):
    def test_audit_round_trip(self) -> None:
        from ambiguity_manager.data_audit.config import get_audit_spec, validate_audit_result
        from ambiguity_manager.data_audit.runner import audit_dataset_entry

        raw = self.tmp_path / "data" / "raw" / "fixture_ds"
        raw.mkdir(parents=True)
        (raw / "primary.csv").write_text("id,name\n1,a\n2,b\n", encoding="utf-8")

        register_entry = {
            "dataset_id": "fixture_ds",
            "display_name": "Fixture",
            "decision": "include",
            "role": "core",
            "reason": "test",
            "expected_converter_ticket": "T99",
            "authoritative_paths": ["data/raw/fixture_ds/primary.csv"],
            "auxiliary_paths": [],
            "split_eligibility": {
                "train": True,
                "dev": True,
                "test": False,
                "gold": False,
                "challenge": False,
            },
            "conditions": [],
            "mapping_confidence": "TODO_VERIFY",
            "supported_labels": [],
            "unsupported_labels": [],
            "blocked_reason": None,
        }
        spec = get_audit_spec("fixture_ds") or {
            "raw_root": "fixture_ds",
            "entry_type": "directory",
            "primary": {
                "relative_path": "data/raw/fixture_ds/primary.csv",
                "file_type": "csv",
                "critical_fields": ["id", "name"],
                "id_fields": ["id"],
            },
            "auxiliary": [],
            "split_structure": "single_file",
            "mapping_risks": [],
        }
        result = audit_dataset_entry(
            repo_root=self.tmp_path,
            entry=register_entry,
            spec=spec,
            licence_entry={
                "dataset_id": "fixture_ds",
                "licence_status": "unresolved",
                "licence_identifier": None,
                "licence_file_relpath": None,
                "licence_text_excerpt": None,
                "licence_url": None,
                "redistribution_allowed": None,
                "attribution_required": None,
                "commercial_use_allowed": None,
                "source_urls": [],
                "citations": [],
                "acquisition_date": None,
                "acquisition_method": "unknown",
                "source_version": None,
                "verified_by": None,
                "verified_at": None,
                "notes": "",
            },
        )
        errors = validate_audit_result({"audit_schema_version": "1.1.0", "datasets": [result]})
        self.assertEqual(errors, [])
        self.assertNotIn("sample_rows", json.dumps(result))
        self.assertEqual(result["payload_verification_status"], "verified")

    def test_missing_authoritative_file_detected(self) -> None:
        from ambiguity_manager.data_audit.runner import audit_dataset_entry

        register_entry = {
            "dataset_id": "fixture_ds",
            "display_name": "Fixture",
            "decision": "include",
            "role": "core",
            "reason": "test",
            "expected_converter_ticket": "T99",
            "authoritative_paths": ["data/raw/fixture_ds/missing.csv"],
            "auxiliary_paths": [],
            "split_eligibility": {
                "train": True,
                "dev": True,
                "test": False,
                "gold": False,
                "challenge": False,
            },
            "conditions": [],
            "mapping_confidence": "TODO_VERIFY",
            "supported_labels": [],
            "unsupported_labels": [],
            "blocked_reason": None,
        }
        result = audit_dataset_entry(
            repo_root=self.tmp_path,
            entry=register_entry,
            spec={
                "raw_root": "fixture_ds",
                "entry_type": "directory",
                "primary": {
                    "relative_path": "data/raw/fixture_ds/missing.csv",
                    "file_type": "csv",
                    "critical_fields": ["id"],
                    "id_fields": ["id"],
                },
                "auxiliary": [],
                "split_structure": "single_file",
                "mapping_risks": [],
            },
            licence_entry={"dataset_id": "fixture_ds", "licence_status": "unresolved"},
        )
        self.assertEqual(result["payload_verification_status"], "blocked")
        self.assertTrue(any(i["code"] == "missing_file" for i in result["issues"]))


class PyarrowCapabilityTests(unittest.TestCase):
    def test_arrow_blocked_when_pyarrow_missing(self) -> None:
        from ambiguity_manager.data_audit.readers import read_arrow_stream_audit

        with mock.patch.dict("sys.modules", {"pyarrow": None, "pyarrow.ipc": None}):
            with mock.patch(
                "ambiguity_manager.data_audit.readers._pyarrow_available",
                return_value=False,
            ):
                result = read_arrow_stream_audit(FIXTURES / "tiny.csv")
                self.assertFalse(result.ok)
                self.assertEqual(result.error_kind, "pyarrow_not_installed")


if __name__ == "__main__":
    unittest.main()
