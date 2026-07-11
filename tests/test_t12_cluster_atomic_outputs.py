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


class T12ClusterAtomicOutputsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.output_dir = Path(self._tmpdir.name)

    def _write(self, *, allow_overwrite: bool = False, status: str = "completed"):
        records = [{"record_id": "a", "value": 1}, {"record_id": "b", "value": 2}]
        return write_shard_outputs(
            output_dir=self.output_dir,
            run_id="run-001",
            shard_id="shard-000",
            input_plan_hash="plan-hash",
            input_shard_hash="shard-hash",
            expected_ids=("a", "b"),
            output_records=records,
            status=status,
            start_timestamp="2026-07-11T18:00:00Z",
            end_timestamp="2026-07-11T18:01:00Z",
            backend_identifier="synthetic-test",
            model_revision=_EXPECTED["model_revision"],
            container_sha256=_EXPECTED["container_sha256"],
            allow_overwrite=allow_overwrite,
        )

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
                backend_identifier="synthetic-test",
                model_revision=_EXPECTED["model_revision"],
                container_sha256=_EXPECTED["container_sha256"],
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


if __name__ == "__main__":
    unittest.main()
