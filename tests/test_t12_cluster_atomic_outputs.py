"""CPU tests for T12 atomic shard output protocol."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ambiguity_manager.model.cluster.atomic_outputs import (
    AtomicOutputError,
    is_temporary_output,
    write_shard_outputs,
)
from ambiguity_manager.model.cluster.identities import _EXPECTED

_MANIFEST_IDENTITY = {
    "backend_identifier": "synthetic-test",
    "backend_config_hash": "backend-hash",
    "model_repository": _EXPECTED["model_repository"],
    "model_revision": _EXPECTED["model_revision"],
    "container_sha256": _EXPECTED["container_sha256"],
}


class T12ClusterAtomicOutputsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.output_dir = Path(self._tmpdir.name)

    def _write(self, *, allow_overwrite: bool = False, status: str = "completed", **overrides):
        records = [{"record_id": "a", "value": 1}, {"record_id": "b", "value": 2}]
        kwargs = {
            "output_dir": self.output_dir,
            "run_id": "run-001",
            "shard_id": "shard-000",
            "input_plan_hash": "plan-hash",
            "input_shard_hash": "shard-hash",
            "expected_ids": ("a", "b"),
            "output_records": records,
            "status": status,
            "start_timestamp": "2026-07-11T18:00:00Z",
            "end_timestamp": "2026-07-11T18:01:00Z",
            **_MANIFEST_IDENTITY,
            "allow_overwrite": allow_overwrite,
        }
        kwargs.update(overrides)
        return write_shard_outputs(**kwargs)

    def test_valid_write_is_atomic(self) -> None:
        manifest = self._write()
        parsed = Path(manifest.parsed_output_path)
        self.assertTrue(parsed.is_file())
        self.assertFalse(any(is_temporary_output(path) for path in self.output_dir.iterdir()))

    def test_temporary_output_not_complete(self) -> None:
        temp = self.output_dir / "shard-000.parsed.jsonl.tmp"
        temp.write_text('{"record_id":"a"}\n', encoding="utf-8")
        self.assertTrue(is_temporary_output(temp))
        self.assertFalse((self.output_dir / "shard-000.manifest.json").exists())

    def test_invalid_output_never_replaces_valid_output(self) -> None:
        self._write()
        parsed = self.output_dir / "shard-000.parsed.jsonl"
        original = parsed.read_text(encoding="utf-8")
        with self.assertRaises(AtomicOutputError):
            write_shard_outputs(
                output_dir=self.output_dir,
                run_id="run-001",
                shard_id="shard-000",
                input_plan_hash="plan-hash",
                input_shard_hash="shard-hash",
                expected_ids=("a", "b"),
                output_records=[{"record_id": "a"}],
                status="completed",
                start_timestamp="2026-07-11T18:00:00Z",
                end_timestamp="2026-07-11T18:01:00Z",
                **_MANIFEST_IDENTITY,
                allow_overwrite=False,
            )
        self.assertEqual(parsed.read_text(encoding="utf-8"), original)

    def test_conflicting_completed_shard_not_overwritten(self) -> None:
        self._write()
        with self.assertRaises(AtomicOutputError):
            self._write()

    def test_manifest_written_after_final_output(self) -> None:
        manifest = self._write()
        manifest_path = self.output_dir / "shard-000.manifest.json"
        self.assertTrue(manifest_path.is_file())
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["output_sha256"], manifest.output_sha256)
        self.assertEqual(payload["status"], "completed")

    def test_completed_manifest_persists_model_repository(self) -> None:
        manifest = self._write()
        self.assertEqual(manifest.model_repository, _EXPECTED["model_repository"])
        payload = json.loads((self.output_dir / "shard-000.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["model_repository"], _EXPECTED["model_repository"])

    def test_completed_manifest_persists_backend_config_hash(self) -> None:
        manifest = self._write()
        self.assertEqual(manifest.backend_config_hash, "backend-hash")
        payload = json.loads((self.output_dir / "shard-000.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["backend_config_hash"], "backend-hash")

    def test_failed_manifest_persists_identity_fields(self) -> None:
        manifest = self._write(status="failed", failure_reasons=("generation_failed",))
        self.assertEqual(manifest.model_repository, _EXPECTED["model_repository"])
        self.assertEqual(manifest.backend_config_hash, "backend-hash")

    def test_incomplete_manifest_persists_identity_fields(self) -> None:
        manifest = self._write(status="incomplete", failure_reasons=("incomplete_output",))
        self.assertEqual(manifest.model_repository, _EXPECTED["model_repository"])
        self.assertEqual(manifest.backend_config_hash, "backend-hash")

    def test_manifest_roundtrip_retains_identity_fields(self) -> None:
        manifest = self._write()
        payload = json.loads((self.output_dir / "shard-000.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["model_repository"], manifest.model_repository)
        self.assertEqual(payload["backend_config_hash"], manifest.backend_config_hash)
        self.assertEqual(payload["backend_identifier"], manifest.backend_identifier)

    def test_first_failed_attempt_records_explicit_failure_reason(self) -> None:
        records = [
            {"record_id": "a", "value": 1},
            {"record_id": "b", "value": 2, "generation_status": "failure"},
        ]
        manifest = self._write(
            status="failed",
            failure_reasons=("missing_or_failed:b",),
            output_records=records,
            failed_ids=("b",),
        )
        self.assertEqual(manifest.status, "failed")
        self.assertEqual(manifest.retry_count, 0)
        self.assertEqual(manifest.attempt_history, ())

    def test_successful_retry_preserves_prior_failure_entry(self) -> None:
        records = [
            {"record_id": "a", "value": 1},
            {"record_id": "b", "value": 2, "generation_status": "failure"},
        ]
        self._write(
            status="failed",
            failure_reasons=("missing_or_failed:b",),
            output_records=records,
            failed_ids=("b",),
        )
        completed = self._write(allow_overwrite=True)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(len(completed.attempt_history), 1)
        self.assertEqual(completed.attempt_history[0].status, "failed")
        self.assertIn("missing_or_failed:b", completed.attempt_history[0].failure_reasons)
        self.assertEqual(completed.retry_count, 1)
        self.assertTrue(completed.attempt_history[0].prior_manifest_sha256)

    def test_retry_count_agrees_with_attempt_history(self) -> None:
        records = [
            {"record_id": "a", "value": 1},
            {"record_id": "b", "value": 2, "generation_status": "failure"},
        ]
        self._write(status="failed", failure_reasons=("boom",), output_records=records, failed_ids=("b",))
        self._write(
            status="failed",
            failure_reasons=("boom-again",),
            output_records=records,
            failed_ids=("b",),
            allow_overwrite=True,
        )
        manifest = self._write(allow_overwrite=True)
        self.assertEqual(manifest.retry_count, len(manifest.attempt_history))
        self.assertEqual(manifest.retry_count, 2)

    def test_multiple_failed_retries_retain_prior_failures_in_order(self) -> None:
        records = [
            {"record_id": "a", "value": 1},
            {"record_id": "b", "value": 2, "generation_status": "failure"},
        ]
        self._write(status="failed", failure_reasons=("first-failure",), output_records=records, failed_ids=("b",))
        self._write(
            status="failed",
            failure_reasons=("second-failure",),
            output_records=records,
            failed_ids=("b",),
            allow_overwrite=True,
        )
        manifest = self._write(
            status="failed",
            failure_reasons=("third-failure",),
            output_records=records,
            failed_ids=("b",),
            allow_overwrite=True,
        )
        reasons = tuple(entry.failure_reasons[0] for entry in manifest.attempt_history)
        self.assertEqual(reasons, ("first-failure", "second-failure"))


if __name__ == "__main__":
    unittest.main()
