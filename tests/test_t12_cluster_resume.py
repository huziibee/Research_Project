"""CPU tests for T12 cluster shard resume decisions."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ambiguity_manager.model.cluster.atomic_outputs import write_shard_outputs
from ambiguity_manager.model.cluster.identities import _EXPECTED
from ambiguity_manager.model.cluster.run_state import (
    ResumeIdentity,
    ShardRunDecision,
    evaluate_resume,
    load_manifest,
    merge_completed_shards,
)

_MANIFEST_IDENTITY = {
    "backend_identifier": "synthetic-test",
    "backend_config_hash": "backend-hash",
    "model_repository": _EXPECTED["model_repository"],
    "model_revision": _EXPECTED["model_revision"],
    "container_sha256": _EXPECTED["container_sha256"],
}


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
            backend_config_hash="backend-hash",
            model_repository=_EXPECTED["model_repository"],
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
            "backend_identifier": "synthetic-test",
            "backend_config_hash": "backend-hash",
            "model_repository": _EXPECTED["model_repository"],
            "model_revision": _EXPECTED["model_revision"],
            "container_sha256": _EXPECTED["container_sha256"],
        }
        base.update(overrides)
        return ResumeIdentity(**base)

    def test_exact_completed_shard_is_skipped(self) -> None:
        decision = evaluate_resume(self.manifest, identity=self._identity(), parsed_output_path=self.parsed_path)
        self.assertTrue(decision.skip)
        self.assertEqual(decision.decision, ShardRunDecision.SKIP_EXACT_COMPLETED)
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
            backend_config_hash="backend-hash",
            model_repository=_EXPECTED["model_repository"],
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
        self.assertEqual(decision.decision, ShardRunDecision.RETRY_FAILED)
        self.assertEqual(decision.reason, "retry_failed_shard")

    def test_different_model_revision_not_skipped(self) -> None:
        decision = evaluate_resume(
            self.manifest,
            identity=self._identity(model_revision="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"),
            parsed_output_path=self.parsed_path,
        )
        self.assertFalse(decision.skip)
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_COMPLETED_CONFLICT)
        self.assertEqual(decision.reason, "completed_conflict:model_revision")

    def test_different_container_sha_not_skipped(self) -> None:
        decision = evaluate_resume(
            self.manifest,
            identity=self._identity(container_sha256="0" * 64),
            parsed_output_path=self.parsed_path,
        )
        self.assertFalse(decision.skip)
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_COMPLETED_CONFLICT)
        self.assertEqual(decision.reason, "completed_conflict:container_sha256")

    def test_different_input_hash_not_skipped(self) -> None:
        decision = evaluate_resume(
            self.manifest,
            identity=self._identity(input_shard_hash="other-hash"),
            parsed_output_path=self.parsed_path,
        )
        self.assertFalse(decision.skip)
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_COMPLETED_CONFLICT)
        self.assertEqual(decision.reason, "completed_conflict:input_shard_hash")

    def test_corrupted_output_hash_not_skipped(self) -> None:
        decision = evaluate_resume(
            self.manifest,
            identity=self._identity(output_sha256="0" * 64),
            parsed_output_path=self.parsed_path,
        )
        self.assertFalse(decision.skip)
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_COMPLETED_CONFLICT)
        self.assertEqual(decision.reason, "completed_conflict:output_sha256")

    def test_different_run_id_blocks_completed_conflict(self) -> None:
        decision = evaluate_resume(
            self.manifest,
            identity=self._identity(run_id="run-002"),
            parsed_output_path=self.parsed_path,
        )
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_COMPLETED_CONFLICT)
        self.assertEqual(decision.reason, "completed_conflict:run_id")

    def test_different_input_plan_hash_blocks_completed_conflict(self) -> None:
        decision = evaluate_resume(
            self.manifest,
            identity=self._identity(input_plan_hash="other-plan"),
            parsed_output_path=self.parsed_path,
        )
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_COMPLETED_CONFLICT)
        self.assertEqual(decision.reason, "completed_conflict:input_plan_hash")

    def test_missing_completed_output_blocks_corruption(self) -> None:
        self.parsed_path.unlink()
        decision = evaluate_resume(
            self.manifest,
            identity=self._identity(),
            parsed_output_path=self.parsed_path,
        )
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_CORRUPTED_COMPLETION)
        self.assertEqual(decision.reason, "corrupted_completion:parsed_output_missing")

    def test_output_file_hash_mismatch_blocks_corruption(self) -> None:
        self.parsed_path.write_text('{"record_id":"tampered"}\n', encoding="utf-8")
        decision = evaluate_resume(
            self.manifest,
            identity=self._identity(),
            parsed_output_path=self.parsed_path,
        )
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_CORRUPTED_COMPLETION)
        self.assertEqual(decision.reason, "corrupted_completion:output_file_sha256")

    def test_failed_shard_with_matching_identity_is_retryable(self) -> None:
        failed_manifest = write_shard_outputs(
            output_dir=self.output_dir / "retry-failed",
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
            backend_config_hash="backend-hash",
            model_repository=_EXPECTED["model_repository"],
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
        self.assertEqual(decision.decision, ShardRunDecision.RETRY_FAILED)
        self.assertTrue(decision.starts_backend)

    def test_incomplete_shard_with_matching_identity_is_retryable(self) -> None:
        incomplete_manifest = write_shard_outputs(
            output_dir=self.output_dir / "retry-incomplete",
            run_id="run-001",
            shard_id="shard-002",
            input_plan_hash="plan-hash",
            input_shard_hash="shard-hash-3",
            expected_ids=("d",),
            output_records=[{"record_id": "d", "value": 4}],
            status="incomplete",
            start_timestamp="2026-07-11T18:00:00Z",
            end_timestamp="2026-07-11T18:01:00Z",
            backend_identifier="synthetic-test",
            backend_config_hash="backend-hash",
            model_repository=_EXPECTED["model_repository"],
            model_revision=_EXPECTED["model_revision"],
            container_sha256=_EXPECTED["container_sha256"],
        )
        decision = evaluate_resume(
            incomplete_manifest,
            identity=self._identity(
                shard_id="shard-002",
                expected_record_ids=("d",),
                output_record_count=1,
                input_shard_hash="shard-hash-3",
                output_sha256=incomplete_manifest.output_sha256,
            ),
            parsed_output_path=Path(incomplete_manifest.parsed_output_path),
        )
        self.assertEqual(decision.decision, ShardRunDecision.RETRY_INCOMPLETE)
        self.assertTrue(decision.starts_backend)

    def test_failed_shard_identity_mismatch_blocks_retry(self) -> None:
        failed_manifest = write_shard_outputs(
            output_dir=self.output_dir / "retry-block",
            run_id="run-001",
            shard_id="shard-003",
            input_plan_hash="plan-hash",
            input_shard_hash="shard-hash-4",
            expected_ids=("e",),
            output_records=[{"record_id": "e", "value": 5}],
            status="failed",
            start_timestamp="2026-07-11T18:00:00Z",
            end_timestamp="2026-07-11T18:01:00Z",
            backend_identifier="synthetic-test",
            backend_config_hash="backend-hash",
            model_repository=_EXPECTED["model_repository"],
            model_revision=_EXPECTED["model_revision"],
            container_sha256=_EXPECTED["container_sha256"],
        )
        decision = evaluate_resume(
            failed_manifest,
            identity=self._identity(
                shard_id="shard-003",
                expected_record_ids=("e",),
                output_record_count=1,
                input_shard_hash="different-shard-hash",
                output_sha256=failed_manifest.output_sha256,
            ),
            parsed_output_path=Path(failed_manifest.parsed_output_path),
        )
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_IDENTITY_MISMATCH)
        self.assertFalse(decision.starts_backend)

    def test_manifest_roundtrip(self) -> None:
        manifest_path = self.output_dir / "shard-000.manifest.json"
        loaded = load_manifest(manifest_path)
        self.assertEqual(loaded.run_id, "run-001")
        self.assertEqual(loaded.model_repository, _EXPECTED["model_repository"])
        self.assertEqual(loaded.backend_config_hash, "backend-hash")

    def test_exact_same_repository_and_config_hash_skips(self) -> None:
        decision = evaluate_resume(
            self.manifest,
            identity=self._identity(
                backend_identifier="synthetic-test",
                backend_config_hash="backend-hash",
            ),
            parsed_output_path=self.parsed_path,
        )
        self.assertEqual(decision.decision, ShardRunDecision.SKIP_EXACT_COMPLETED)

    def test_different_model_repository_blocks_completed_conflict(self) -> None:
        decision = evaluate_resume(
            self.manifest,
            identity=self._identity(model_repository="Other/Model"),
            parsed_output_path=self.parsed_path,
        )
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_COMPLETED_CONFLICT)
        self.assertEqual(decision.reason, "completed_conflict:model_repository")

    def test_different_backend_config_hash_blocks_completed_conflict(self) -> None:
        decision = evaluate_resume(
            self.manifest,
            identity=self._identity(backend_config_hash="other-config-hash"),
            parsed_output_path=self.parsed_path,
        )
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_COMPLETED_CONFLICT)
        self.assertEqual(decision.reason, "completed_conflict:backend_config_hash")

    def test_different_backend_identifier_blocks_completed_conflict(self) -> None:
        decision = evaluate_resume(
            self.manifest,
            identity=self._identity(backend_identifier="other-backend"),
            parsed_output_path=self.parsed_path,
        )
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_COMPLETED_CONFLICT)
        self.assertEqual(decision.reason, "completed_conflict:backend_identifier")

    def test_missing_model_repository_blocks_completed_manifest(self) -> None:
        payload = json.loads((self.output_dir / "shard-000.manifest.json").read_text(encoding="utf-8"))
        del payload["model_repository"]
        (self.output_dir / "shard-000.manifest.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
        legacy = load_manifest(self.output_dir / "shard-000.manifest.json")
        decision = evaluate_resume(legacy, identity=self._identity(), parsed_output_path=self.parsed_path)
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_CORRUPTED_COMPLETION)
        self.assertEqual(decision.reason, "corrupted_completion:missing_model_repository")

    def test_missing_backend_config_hash_blocks_completed_manifest(self) -> None:
        payload = json.loads((self.output_dir / "shard-000.manifest.json").read_text(encoding="utf-8"))
        del payload["backend_config_hash"]
        (self.output_dir / "shard-000.manifest.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
        legacy = load_manifest(self.output_dir / "shard-000.manifest.json")
        decision = evaluate_resume(legacy, identity=self._identity(), parsed_output_path=self.parsed_path)
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_CORRUPTED_COMPLETION)
        self.assertEqual(decision.reason, "corrupted_completion:missing_backend_config_hash")

    def test_failed_shard_different_model_repository_not_retryable(self) -> None:
        failed_manifest = write_shard_outputs(
            output_dir=self.output_dir / "repo-mismatch",
            run_id="run-001",
            shard_id="shard-010",
            input_plan_hash="plan-hash",
            input_shard_hash="shard-hash-10",
            expected_ids=("z",),
            output_records=[{"record_id": "z", "value": 10}],
            status="failed",
            start_timestamp="2026-07-11T18:00:00Z",
            end_timestamp="2026-07-11T18:01:00Z",
            **_MANIFEST_IDENTITY,
        )
        decision = evaluate_resume(
            failed_manifest,
            identity=self._identity(
                shard_id="shard-010",
                expected_record_ids=("z",),
                output_record_count=1,
                input_shard_hash="shard-hash-10",
                output_sha256=failed_manifest.output_sha256,
                model_repository="Other/Model",
            ),
            parsed_output_path=Path(failed_manifest.parsed_output_path),
        )
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_IDENTITY_MISMATCH)
        self.assertEqual(decision.reason, "identity_mismatch:model_repository")

    def test_failed_shard_different_backend_config_hash_not_retryable(self) -> None:
        failed_manifest = write_shard_outputs(
            output_dir=self.output_dir / "config-mismatch",
            run_id="run-001",
            shard_id="shard-011",
            input_plan_hash="plan-hash",
            input_shard_hash="shard-hash-11",
            expected_ids=("y",),
            output_records=[{"record_id": "y", "value": 11}],
            status="failed",
            start_timestamp="2026-07-11T18:00:00Z",
            end_timestamp="2026-07-11T18:01:00Z",
            **_MANIFEST_IDENTITY,
        )
        decision = evaluate_resume(
            failed_manifest,
            identity=self._identity(
                shard_id="shard-011",
                expected_record_ids=("y",),
                output_record_count=1,
                input_shard_hash="shard-hash-11",
                output_sha256=failed_manifest.output_sha256,
                backend_config_hash="other-config-hash",
            ),
            parsed_output_path=Path(failed_manifest.parsed_output_path),
        )
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_IDENTITY_MISMATCH)
        self.assertEqual(decision.reason, "identity_mismatch:backend_config_hash")

    def test_failed_manifest_missing_identity_not_retryable(self) -> None:
        write_shard_outputs(
            output_dir=self.output_dir / "legacy-failed",
            run_id="run-001",
            shard_id="shard-012",
            input_plan_hash="plan-hash",
            input_shard_hash="shard-hash-12",
            expected_ids=("w",),
            output_records=[{"record_id": "w", "value": 12}],
            status="failed",
            start_timestamp="2026-07-11T18:00:00Z",
            end_timestamp="2026-07-11T18:01:00Z",
            **_MANIFEST_IDENTITY,
        )
        legacy_payload = json.loads(
            (self.output_dir / "legacy-failed" / "shard-012.manifest.json").read_text(encoding="utf-8")
        )
        del legacy_payload["backend_config_hash"]
        (self.output_dir / "legacy-failed" / "shard-012.manifest.json").write_text(
            json.dumps(legacy_payload) + "\n",
            encoding="utf-8",
        )
        legacy = load_manifest(self.output_dir / "legacy-failed" / "shard-012.manifest.json")
        decision = evaluate_resume(
            legacy,
            identity=self._identity(
                shard_id="shard-012",
                expected_record_ids=("w",),
                output_record_count=1,
                input_shard_hash="shard-hash-12",
                output_sha256=legacy.output_sha256,
            ),
            parsed_output_path=Path(legacy.parsed_output_path),
        )
        self.assertEqual(decision.decision, ShardRunDecision.BLOCK_IDENTITY_MISMATCH)
        self.assertEqual(decision.reason, "identity_mismatch:missing_backend_config_hash")


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
            backend_config_hash="backend-hash",
            model_repository=_EXPECTED["model_repository"],
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
