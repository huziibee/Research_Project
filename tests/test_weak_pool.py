"""Tests for the T09 weak pool builder."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ambiguity_manager.data_audit.readers import streaming_sha256
from ambiguity_manager.paths import repo_relative_path
from ambiguity_manager.schema.records import canonical_record_from_dict, canonical_record_to_dict
from ambiguity_manager.weak_pool import (
    DATASET_ROLE_CONFIG,
    DatasetInputSpec,
    WeakPoolBuildError,
    WeakPoolOutputSpec,
    build_weak_pool,
)

FIXTURES = Path(__file__).parent / "fixtures" / "weak_pool"


class WeakPoolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        (self.root / "pyproject.toml").write_text("[project]\nname='tmp'\n", encoding="utf-8")
        self.pool_dir = self.root / "data" / "processed" / "weak_pool"
        self.metrics_dir = self.root / "outputs" / "metrics"
        self.manifests_dir = self.root / "outputs" / "manifests"
        self.interim_dir = self.root / "data" / "interim"
        for directory in (self.pool_dir, self.metrics_dir, self.manifests_dir, self.interim_dir):
            directory.mkdir(parents=True, exist_ok=True)

        patcher = mock.patch("ambiguity_manager.paths.repo_root", return_value=self.root.resolve())
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write_summary(
        self,
        dataset_id: str,
        canonical_path: Path,
        rows_converted: int,
        mapping_version: str,
    ) -> Path:
        summary_path = self.metrics_dir / f"{dataset_id}_conversion_summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "rows_converted": rows_converted,
                    "output_path": repo_relative_path(canonical_path),
                    "mapping_version": mapping_version,
                    "schema_version": "1.0.0",
                }
            ),
            encoding="utf-8",
        )
        return summary_path

    def _install_dataset(self, dataset_id: str, fixture_name: str | None = None) -> DatasetInputSpec:
        fixture_name = fixture_name or f"tiny_{dataset_id}.jsonl"
        canonical_path = (self.interim_dir / dataset_id / f"{dataset_id}_canonical.jsonl").resolve()
        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIXTURES / fixture_name, canonical_path)
        rows = sum(1 for line in canonical_path.read_text(encoding="utf-8").splitlines() if line.strip())
        self._write_summary(
            dataset_id,
            canonical_path,
            rows,
            DATASET_ROLE_CONFIG[dataset_id]["mapping_version"],
        )
        return DatasetInputSpec(
            dataset_id=dataset_id,
            canonical_path=canonical_path,
            summary_path=self.metrics_dir / f"{dataset_id}_conversion_summary.json",
        )

    def _outputs(self) -> WeakPoolOutputSpec:
        return WeakPoolOutputSpec(
            primary_path=self.pool_dir / "weak_pool_canonical.jsonl",
            auxiliary_path=self.pool_dir / "weak_pool_auxiliary.jsonl",
            membership_path=self.pool_dir / "weak_pool_membership.jsonl",
            manifest_path=self.manifests_dir / "weak_pool_manifest.json",
            summary_path=self.metrics_dir / "weak_pool_summary.json",
        )

    def _full_inputs(self) -> list[DatasetInputSpec]:
        return [
            self._install_dataset("ambik"),
            self._install_dataset("indirect_requests"),
            self._install_dataset("codraw_icr_v2"),
            self._install_dataset("vague"),
            self._install_dataset("clara"),
            self._install_dataset("clariq"),
        ]

    def _read_jsonl_ids(self, path: Path) -> list[str]:
        return [json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_successful_primary_and_auxiliary_partitioning(self) -> None:
        result = build_weak_pool(self._full_inputs(), self._outputs())
        self.assertEqual(result["primary_count"], 5)
        self.assertEqual(result["auxiliary_count"], 1)
        self.assertEqual(result["membership_count"], 6)
        primary_ids = set(self._read_jsonl_ids(self.pool_dir / "weak_pool_canonical.jsonl"))
        auxiliary_ids = set(self._read_jsonl_ids(self.pool_dir / "weak_pool_auxiliary.jsonl"))
        self.assertNotIn("clariq:train:1:F0001:Q00384:abc", primary_ids)
        self.assertIn("clariq:train:1:F0001:Q00384:abc", auxiliary_ids)

    def test_membership_status_fields(self) -> None:
        build_weak_pool(self._full_inputs(), self._outputs())
        rows = [
            json.loads(line)
            for line in (self.pool_dir / "weak_pool_membership.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        by_id = {row["id"]: row for row in rows}
        self.assertEqual(by_id["ambik:1"]["core_pool_status"], "eligible")
        self.assertEqual(by_id["clara:1"]["core_pool_status"], "conditional_pending")
        self.assertEqual(by_id["clariq:train:1:F0001:Q00384:abc"]["core_pool_status"], "ineligible")
        self.assertEqual(by_id["clariq:train:1:F0001:Q00384:abc"]["physical_pool"], "auxiliary")

    def test_record_preservation(self) -> None:
        inputs = self._full_inputs()
        input_records: dict[str, dict] = {}
        for spec in inputs:
            for line in spec.canonical_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    record = canonical_record_from_dict(json.loads(line))
                    input_records[record.id] = canonical_record_to_dict(record)
        build_weak_pool(inputs, self._outputs())
        for pool_name in ("weak_pool_canonical.jsonl", "weak_pool_auxiliary.jsonl"):
            for line in (self.pool_dir / pool_name).read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = canonical_record_from_dict(json.loads(line))
                self.assertEqual(canonical_record_to_dict(record), input_records[record.id])

    def test_fixed_dataset_ordering(self) -> None:
        build_weak_pool(self._full_inputs(), self._outputs())
        primary_ids = self._read_jsonl_ids(self.pool_dir / "weak_pool_canonical.jsonl")
        self.assertEqual(
            primary_ids,
            ["ambik:1", "indirect_requests:train:0", "codraw_icr_v2:1", "vague:img1", "clara:1"],
        )

    def test_input_file_order_does_not_change_output(self) -> None:
        inputs = self._full_inputs()
        first = build_weak_pool(list(reversed(inputs)), self._outputs())
        first_hash = streaming_sha256(self.pool_dir / "weak_pool_canonical.jsonl")
        second = build_weak_pool(inputs, self._outputs())
        second_hash = streaming_sha256(self.pool_dir / "weak_pool_canonical.jsonl")
        self.assertEqual(first_hash, second_hash)
        self.assertEqual(first["output_sha256"], second["output_sha256"])

    def test_input_row_order_does_not_change_output(self) -> None:
        inputs = self._full_inputs()
        build_weak_pool(inputs, self._outputs())
        baseline_hash = streaming_sha256(self.pool_dir / "weak_pool_canonical.jsonl")
        reversed_lines = list(reversed(inputs[0].canonical_path.read_text(encoding="utf-8").splitlines()))
        inputs[0].canonical_path.write_text("\n".join(reversed_lines) + "\n", encoding="utf-8")
        build_weak_pool(inputs, self._outputs())
        self.assertEqual(baseline_hash, streaming_sha256(self.pool_dir / "weak_pool_canonical.jsonl"))

    def test_deterministic_machine_artefacts(self) -> None:
        inputs = self._full_inputs()
        build_weak_pool(inputs, self._outputs())
        hashes = {
            "primary": streaming_sha256(self.pool_dir / "weak_pool_canonical.jsonl"),
            "auxiliary": streaming_sha256(self.pool_dir / "weak_pool_auxiliary.jsonl"),
            "membership": streaming_sha256(self.pool_dir / "weak_pool_membership.jsonl"),
            "manifest": streaming_sha256(self.manifests_dir / "weak_pool_manifest.json"),
            "summary": streaming_sha256(self.metrics_dir / "weak_pool_summary.json"),
        }
        build_weak_pool(inputs, self._outputs())
        self.assertEqual(hashes["primary"], streaming_sha256(self.pool_dir / "weak_pool_canonical.jsonl"))
        self.assertEqual(hashes["auxiliary"], streaming_sha256(self.pool_dir / "weak_pool_auxiliary.jsonl"))
        self.assertEqual(hashes["membership"], streaming_sha256(self.pool_dir / "weak_pool_membership.jsonl"))
        self.assertEqual(hashes["manifest"], streaming_sha256(self.manifests_dir / "weak_pool_manifest.json"))
        self.assertEqual(hashes["summary"], streaming_sha256(self.metrics_dir / "weak_pool_summary.json"))
        manifest = json.loads((self.manifests_dir / "weak_pool_manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("build_timestamp", manifest)
        self.assertNotIn("source_git_commit", manifest)

    def test_disjointness_and_union(self) -> None:
        result = build_weak_pool(self._full_inputs(), self._outputs())
        checks = result["accounting_checks"]
        self.assertTrue(checks["primary_auxiliary_disjoint"])
        self.assertTrue(checks["membership_equals_union"])

    def test_missing_input_fails_without_output(self) -> None:
        inputs = self._full_inputs()[:5]
        with self.assertRaises(WeakPoolBuildError):
            build_weak_pool(inputs, self._outputs())

    def test_missing_summary_fails(self) -> None:
        inputs = self._full_inputs()
        inputs[0].summary_path.unlink()
        with self.assertRaises(WeakPoolBuildError):
            build_weak_pool(inputs, self._outputs())

    def test_blank_jsonl_line_fails(self) -> None:
        inputs = self._full_inputs()
        inputs[0].canonical_path.write_text("\n", encoding="utf-8")
        with self.assertRaises(WeakPoolBuildError):
            build_weak_pool(inputs, self._outputs())

    def test_malformed_json_fails(self) -> None:
        inputs = self._full_inputs()
        inputs[0].canonical_path.write_text("{not-json", encoding="utf-8")
        with self.assertRaises(WeakPoolBuildError):
            build_weak_pool(inputs, self._outputs())

    def test_wrong_schema_version_fails(self) -> None:
        inputs = self._full_inputs()
        payload = json.loads(inputs[0].canonical_path.read_text(encoding="utf-8").strip())
        payload["schema_version"] = "9.9.9"
        inputs[0].canonical_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        with self.assertRaises(WeakPoolBuildError):
            build_weak_pool(inputs, self._outputs())

    def test_wrong_record_class_fails(self) -> None:
        inputs = self._full_inputs()
        payload = json.loads(inputs[0].canonical_path.read_text(encoding="utf-8").strip())
        payload["record_class"] = "adjudicated_gold"
        payload["annotation_status"] = "manually_annotated"
        payload["label_confidence"] = "manual_gold"
        inputs[0].canonical_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        with self.assertRaises(WeakPoolBuildError):
            build_weak_pool(inputs, self._outputs())

    def test_wrong_source_dataset_fails(self) -> None:
        inputs = self._full_inputs()
        payload = json.loads(inputs[0].canonical_path.read_text(encoding="utf-8").strip())
        payload["source_dataset"] = "clariq"
        inputs[0].canonical_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        with self.assertRaises(WeakPoolBuildError):
            build_weak_pool(inputs, self._outputs())

    def test_empty_source_id_fails(self) -> None:
        inputs = self._full_inputs()
        payload = json.loads(inputs[0].canonical_path.read_text(encoding="utf-8").strip())
        payload["source_id"] = ""
        inputs[0].canonical_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        with self.assertRaises(WeakPoolBuildError):
            build_weak_pool(inputs, self._outputs())

    def test_duplicate_id_within_input_fails(self) -> None:
        inputs = self._full_inputs()
        line = inputs[0].canonical_path.read_text(encoding="utf-8").strip()
        inputs[0].canonical_path.write_text(f"{line}\n{line}\n", encoding="utf-8")
        self._write_summary("ambik", inputs[0].canonical_path, 2, DATASET_ROLE_CONFIG["ambik"]["mapping_version"])
        with self.assertRaises(WeakPoolBuildError):
            build_weak_pool(inputs, self._outputs())

    def test_duplicate_id_across_inputs_fails(self) -> None:
        inputs = self._full_inputs()
        payload = json.loads(inputs[-1].canonical_path.read_text(encoding="utf-8").strip())
        payload["id"] = "ambik:1"
        payload["source_id"] = "dup-cross"
        inputs[-1].canonical_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        with self.assertRaises(WeakPoolBuildError):
            build_weak_pool(inputs, self._outputs())

    def test_summary_count_mismatch_fails(self) -> None:
        inputs = self._full_inputs()
        self._write_summary("ambik", inputs[0].canonical_path, 99, DATASET_ROLE_CONFIG["ambik"]["mapping_version"])
        with self.assertRaises(WeakPoolBuildError):
            build_weak_pool(inputs, self._outputs())

    def test_summary_output_path_mismatch_fails(self) -> None:
        inputs = self._full_inputs()
        self._write_summary(
            "ambik",
            inputs[0].canonical_path.parent / "other.jsonl",
            1,
            DATASET_ROLE_CONFIG["ambik"]["mapping_version"],
        )
        with self.assertRaises(WeakPoolBuildError):
            build_weak_pool(inputs, self._outputs())

    def test_mapping_version_mismatch_fails(self) -> None:
        inputs = self._full_inputs()
        self._write_summary("ambik", inputs[0].canonical_path, 1, "ambik-9.9.9")
        with self.assertRaises(WeakPoolBuildError):
            build_weak_pool(inputs, self._outputs())

    def test_semantic_duplicates_reported_not_removed(self) -> None:
        inputs = self._full_inputs()
        ambik_payload = json.loads(inputs[0].canonical_path.read_text(encoding="utf-8").strip())
        vague_payload = json.loads(inputs[3].canonical_path.read_text(encoding="utf-8").strip())
        vague_payload["command"] = ambik_payload["command"]
        inputs[3].canonical_path.write_text(json.dumps(vague_payload) + "\n", encoding="utf-8")
        result = build_weak_pool(inputs, self._outputs())
        self.assertGreaterEqual(result["overlap_analysis"]["normalized_command_duplicate_groups"], 1)
        self.assertEqual(result["primary_count"], 5)

    def test_no_canonical_role_mutation(self) -> None:
        build_weak_pool(self._full_inputs(), self._outputs())
        for path in (self.pool_dir / "weak_pool_canonical.jsonl", self.pool_dir / "weak_pool_auxiliary.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    payload = json.loads(line)
                    self.assertNotIn("dataset_role", payload)
                    self.assertNotIn("core_pool_status", payload)
                    self.assertNotIn("physical_pool", payload)

    def test_repository_relative_paths_in_manifest(self) -> None:
        build_weak_pool(self._full_inputs(), self._outputs())
        manifest = json.loads((self.manifests_dir / "weak_pool_manifest.json").read_text(encoding="utf-8"))
        for item in manifest["inputs"]:
            self.assertFalse(Path(item["canonical_input_path"]).is_absolute())
        self.assertFalse(Path(manifest["outputs"]["primary_pool_path"]).is_absolute())

    def test_no_raw_text_in_machine_summary(self) -> None:
        build_weak_pool(self._full_inputs(), self._outputs())
        summary_text = (self.metrics_dir / "weak_pool_summary.json").read_text(encoding="utf-8")
        self.assertNotIn("Pick up the cup.", summary_text)
        self.assertNotIn("Tell me about trees.", summary_text)

    def test_failure_leaves_existing_outputs_unchanged(self) -> None:
        inputs = self._full_inputs()
        build_weak_pool(inputs, self._outputs())
        before = {
            path.name: path.read_bytes()
            for path in self.pool_dir.glob("*")
            if path.is_file()
        }
        bad = self._install_dataset("ambik")
        bad.canonical_path.write_text("{bad", encoding="utf-8")
        broken_inputs = [bad, *inputs[1:]]
        with self.assertRaises(WeakPoolBuildError):
            build_weak_pool(broken_inputs, self._outputs())
        after = {
            path.name: path.read_bytes()
            for path in self.pool_dir.glob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)

    def test_temp_files_cleaned_on_failure(self) -> None:
        inputs = self._full_inputs()
        bad = self._install_dataset("ambik")
        bad.canonical_path.write_text("{bad", encoding="utf-8")
        with self.assertRaises(WeakPoolBuildError):
            build_weak_pool([bad, *inputs[1:]], self._outputs())
        self.assertEqual(list(self.pool_dir.glob(".weak_pool_build_*")), [])


class WeakPoolIntegrationTests(unittest.TestCase):
    def test_real_six_input_smoke_when_available(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        required = [
            repo_root / "data/interim/ambik/ambik_canonical.jsonl",
            repo_root / "data/interim/indirect_requests/indirect_requests_canonical.jsonl",
            repo_root / "data/interim/codraw_icr_v2/codraw_icr_v2_canonical.jsonl",
            repo_root / "data/interim/vague/vague_canonical.jsonl",
            repo_root / "data/interim/clara/clara_canonical.jsonl",
            repo_root / "data/interim/clariq/clariq_canonical.jsonl",
        ]
        if not all(path.is_file() for path in required):
            self.skipTest("real canonical inputs not available")
        from ambiguity_manager.weak_pool import production_spec

        inputs, outputs = production_spec(repo_root)
        with mock.patch("ambiguity_manager.paths.repo_root", return_value=repo_root.resolve()):
            result = build_weak_pool(inputs, outputs, publish=True)
        self.assertEqual(result["primary_count"], 15839)
        self.assertEqual(result["auxiliary_count"], 8565)
        self.assertEqual(result["membership_count"], 24404)


if __name__ == "__main__":
    unittest.main()
