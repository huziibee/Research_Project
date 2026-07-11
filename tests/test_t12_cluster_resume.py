"""CPU tests for T12 cluster shard resume decisions."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ambiguity_manager.model.cluster.atomic_outputs import write_shard_outputs
from ambiguity_manager.model.cluster.identities import _EXPECTED
from ambiguity_manager.model.cluster.run_state import ResumeIdentity, evaluate_resume, load_manifest, merge_completed_shards


class T12ClusterResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.output_dir = Path(self._tmpdir.name)
        self.records = [{"record_id": "a", "value": 1}, {"record_id": "b", "value": 2}]
        self.manifest = write_shard_outputs(
            output_dir=self.output_dir,
            run_id="run-001",
            shard_id="shard-000",
            input_plan_hash="plan-hash",
            input_shard_hash="shard-hash",
            expected_ids=("a", "b"),
            output_records=self.records,
            status="completed",
            start_timestamp="2026-07-11T18:00:00Z",
            end_timestamp="2026-07-11T18:01:00Z",
            backend_identifier="synthetic-test",
            model_revision=_EXPECTED["model_revision"],
            container_sha256=_EXPECTED["container_sha256"],
        )
        self.parsed_path = Path(self.manifest.parsed_output_path)

    def _identity(self, **overrides) -> ResumeIdentity:
        base = {
            "run_id": "run-001",
            "shard_id": "shard-000",
            "input_plan_hash": "plan-hash",
            "input_shard_hash": "shard-hash",
            "expected_record_ids": ("a", "b"),
            "output_record_count": 2,
            "output_sha256": self.manifest.output_sha256,
            "model_repository": _EXPECTED["model_repository"],
            "model_revision": _EXPECTED["model_revision"],
            "container_sha256": _EXPECTED["container_sha256"],
            "backend_config_hash": "backend-hash",
        }
        base.update(overrides)
        return ResumeIdentity(**base)

    def test_exact_completed_shard_is_skipped(self) -> None:
        decision = evaluate_resume(self.manifest, identity=self._identity(), parsed_output_path=self.parsed_path)
        self.assertTrue(decision.skip)
        self.assertEqual(decision.reason, "exact_completed_shard")

    def test_failed_shard_is_not_skipped(self) -> None:
        failed_manifest = write_shard_outputs(
            output_dir=self.output_dir / "failed",
            run_id="run-001",
            shard_id="shard-001",
            input_plan_hash="plan-hash",
            input_shard_hash="shard-hash-2",
            expected_ids=("c",),
            output_records=[{"record_id": "c", "value": 3}],
            status="failed",
            start_timestamp="2026-07-11T18:00:00Z",
            end_timestamp="2026-07-11T18:01:00Z",
            backend_identifier="synthetic-test",
            model_revision=_EXPECTED["model_revision"],
            container_sha256=_EXPECTED["container_sha256"],
        )
        decision = evaluate_resume(
            failed_manifest,
            identity=self._identity(
                shard_id="shard-001",
                expected_record_ids=("c",),
                output_record_count=1,
                input_shard_hash="shard-hash-2",
                output_sha256=failed_manifest.output_sha256,
            ),
            parsed_output_path=Path(failed_manifest.parsed_output_path),
        )
        self.assertFalse(decision.skip)
        self.assertEqual(decision.reason, "shard_not_completed")

    def test_different_model_revision_not_skipped(self) -> None:
        decision = evaluate_resume(
            self.manifest,
            identity=self._identity(model_revision="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"),
            parsed_output_path=self.parsed_path,
        )
        self.assertFalse(decision.skip)
        self.assertEqual(decision.reason, "mismatch:model_revision")

    def test_different_container_sha_not_skipped(self) -> None:
        decision = evaluate_resume(
            self.manifest,
            identity=self._identity(container_sha256="0" * 64),
            parsed_output_path=self.parsed_path,
        )
        self.assertFalse(decision.skip)
        self.assertEqual(decision.reason, "mismatch:container_sha256")

    def test_different_input_hash_not_skipped(self) -> None:
        decision = evaluate_resume(
            self.manifest,
            identity=self._identity(input_shard_hash="other-hash"),
            parsed_output_path=self.parsed_path,
        )
        self.assertFalse(decision.skip)
        self.assertEqual(decision.reason, "mismatch:input_shard_hash")

    def test_corrupted_output_hash_not_skipped(self) -> None:
        decision = evaluate_resume(
            self.manifest,
            identity=self._identity(output_sha256="0" * 64),
            parsed_output_path=self.parsed_path,
        )
        self.assertFalse(decision.skip)
        self.assertEqual(decision.reason, "mismatch:output_sha256")

    def test_manifest_roundtrip(self) -> None:
        manifest_path = self.output_dir / "shard-000.manifest.json"
        loaded = load_manifest(manifest_path)
        self.assertEqual(loaded.run_id, "run-001")


class T12ClusterMergeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.output_dir = Path(self._tmpdir.name)

    def _completed_shard(self, shard_id: str, record_ids: tuple[str, ...], directory: Path) -> tuple:
        records = [{"record_id": record_id, "value": record_id} for record_id in record_ids]
        manifest = write_shard_outputs(
            output_dir=directory,
            run_id="run-001",
            shard_id=shard_id,
            input_plan_hash="plan-hash",
            input_shard_hash=f"{shard_id}-hash",
            expected_ids=record_ids,
            output_records=records,
            status="completed",
            start_timestamp="2026-07-11T18:00:00Z",
            end_timestamp="2026-07-11T18:01:00Z",
            backend_identifier="synthetic-test",
            model_revision=_EXPECTED["model_revision"],
            container_sha256=_EXPECTED["container_sha256"],
        )
        return manifest, Path(manifest.parsed_output_path)

    def test_deterministic_merge_hash(self) -> None:
        manifest_a, path_a = self._completed_shard("shard-000", ("a", "b"), self.output_dir / "a")
        manifest_b, path_b = self._completed_shard("shard-001", ("c",), self.output_dir / "b")
        first = merge_completed_shards(
            shard_manifests=[manifest_a, manifest_b],
            parsed_output_paths=[path_a, path_b],
            plan_record_order=("a", "b", "c"),
            output_path=self.output_dir / "merged.jsonl",
            run_id="run-001",
            backend_config_hash="backend-hash",
            model_revision=_EXPECTED["model_revision"],
            container_sha256=_EXPECTED["container_sha256"],
            allow_overwrite=True,
        )
        second = merge_completed_shards(
            shard_manifests=[manifest_a, manifest_b],
            parsed_output_paths=[path_a, path_b],
            plan_record_order=("a", "b", "c"),
            output_path=self.output_dir / "merged-2.jsonl",
            run_id="run-001",
            backend_config_hash="backend-hash",
            model_revision=_EXPECTED["model_revision"],
            container_sha256=_EXPECTED["container_sha256"],
            allow_overwrite=True,
        )
        self.assertEqual(first.merged_sha256, second.merged_sha256)

    def test_duplicate_id_rejected(self) -> None:
        manifest_a, path_a = self._completed_shard("shard-000", ("a",), self.output_dir / "dup-a")
        manifest_b, path_b = self._completed_shard("shard-001", ("a",), self.output_dir / "dup-b")
        result = merge_completed_shards(
            shard_manifests=[manifest_a, manifest_b],
            parsed_output_paths=[path_a, path_b],
            plan_record_order=("a",),
            output_path=self.output_dir / "merged-dup.jsonl",
            run_id="run-001",
            backend_config_hash="backend-hash",
            model_revision=_EXPECTED["model_revision"],
            container_sha256=_EXPECTED["container_sha256"],
        )
        self.assertTrue(any(reason.startswith("duplicate_record_id:") for reason in result.rejection_reasons))

    def test_missing_id_rejected(self) -> None:
        manifest_a, path_a = self._completed_shard("shard-000", ("a",), self.output_dir / "miss")
        result = merge_completed_shards(
            shard_manifests=[manifest_a],
            parsed_output_paths=[path_a],
            plan_record_order=("a", "b"),
            output_path=self.output_dir / "merged-miss.jsonl",
            run_id="run-001",
            backend_config_hash="backend-hash",
            model_revision=_EXPECTED["model_revision"],
            container_sha256=_EXPECTED["container_sha256"],
        )
        self.assertIn("missing_record_id:b", result.rejection_reasons)

    def test_mixed_run_ids_rejected(self) -> None:
        manifest_a, path_a = self._completed_shard("shard-000", ("a",), self.output_dir / "mix-a")
        manifest_b, path_b = self._completed_shard("shard-001", ("b",), self.output_dir / "mix-b")
        payload = json.loads((self.output_dir / "mix-b" / "shard-001.manifest.json").read_text(encoding="utf-8"))
        payload["run_id"] = "run-002"
        (self.output_dir / "mix-b" / "shard-001.manifest.json").write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest_b = load_manifest(self.output_dir / "mix-b" / "shard-001.manifest.json")
        result = merge_completed_shards(
            shard_manifests=[manifest_a, manifest_b],
            parsed_output_paths=[path_a, path_b],
            plan_record_order=("a", "b"),
            output_path=self.output_dir / "merged-mix.jsonl",
            run_id="run-001",
            backend_config_hash="backend-hash",
            model_revision=_EXPECTED["model_revision"],
            container_sha256=_EXPECTED["container_sha256"],
        )
        self.assertIn("mixed_run_ids", result.rejection_reasons)

    def test_original_order_restored(self) -> None:
        manifest_a, path_a = self._completed_shard("shard-000", ("b", "a"), self.output_dir / "ord-a")
        manifest_b, path_b = self._completed_shard("shard-001", ("c",), self.output_dir / "ord-b")
        merged_path = self.output_dir / "merged-order.jsonl"
        result = merge_completed_shards(
            shard_manifests=[manifest_a, manifest_b],
            parsed_output_paths=[path_a, path_b],
            plan_record_order=("a", "b", "c"),
            output_path=merged_path,
            run_id="run-001",
            backend_config_hash="backend-hash",
            model_revision=_EXPECTED["model_revision"],
            container_sha256=_EXPECTED["container_sha256"],
            allow_overwrite=True,
        )
        self.assertEqual(result.status, "pass")
        ids = [
            json.loads(line)["record_id"]
            for line in merged_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(ids, ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
