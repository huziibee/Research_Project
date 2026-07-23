from __future__ import annotations

import json
import sys
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.model.t27c_runtime_recovery import (  # noqa: E402
    Heartbeat,
    PredictionJournal,
    PredictionTimeout,
    RuntimeRecoveryError,
    atomic_write_json,
    freeze_task_timeouts,
    generated_continuation,
    run_bounded,
    verify_adapter_reuse,
)


class T27CRuntimeRecoveryTests(unittest.TestCase):
    def _work_dir(self) -> Path:
        path = ROOT / "outputs" / f".t27c-runtime-test-{uuid.uuid4().hex}"
        path.mkdir(parents=True, exist_ok=False)
        return path

    def test_atomic_heartbeat_and_advancing_timestamp(self) -> None:
        path = self._work_dir() / "heartbeat.json"
        hb = Heartbeat(path, "run-1", 2)
        first = hb.update(phase="generation", status="running", completed_task_call_count=0)
        second = hb.update(phase="generation", status="completed", completed_task_call_count=1)
        self.assertEqual(json.loads(path.read_text())["completed_task_call_count"], 1)
        self.assertLessEqual(first["pid"], second["pid"])
        self.assertIsNotNone(second["latest_successful_output_time"])

    def test_journal_resume_duplicate_and_corruption_guards(self) -> None:
        path = self._work_dir() / "journal.jsonl"
        journal = PredictionJournal(path)
        entry = {
                "mode": "base", "record_id": "r1", "task_id": "predict_cpc_v1",
                "status": "completed", "validation_status": "valid",
            }
        journal.append(entry)
        self.assertIsNotNone(PredictionJournal(path).completed(mode="base", record_id="r1", task_id="predict_cpc_v1"))
        with self.assertRaises(RuntimeRecoveryError):
            journal.append(entry)
        path.write_text(path.read_text() + "{broken\n", encoding="utf-8")
        with self.assertRaises(RuntimeRecoveryError):
            PredictionJournal(path)

    def test_timeout_is_typed_and_does_not_change_other_calls(self) -> None:
        with self.assertRaises(PredictionTimeout):
            run_bounded(lambda: time.sleep(0.05), 0.001)
        self.assertEqual(run_bounded(lambda: "ok", 1), "ok")

    def test_freeze_timeouts_uses_diagnostic_p95_and_registry_only(self) -> None:
        registry = {"tasks": [{"task_id": "a"}, {"task_id": "b"}]}
        result = freeze_task_timeouts({"a": [1, 2, 3, 4], "b": [100]}, registry, declared_minimum_seconds=5, multiplier=3)
        self.assertEqual(result, {"a": 12, "b": 300})
        with self.assertRaises(RuntimeRecoveryError):
            freeze_task_timeouts({"a": [1]}, registry)

    def test_prompt_echo_is_rejected_and_continuation_isolated(self) -> None:
        self.assertEqual(generated_continuation([1, 2], [1, 2, 3]), [3])
        with self.assertRaises(RuntimeRecoveryError):
            generated_continuation([1, 2], [1, 9, 3])

    def test_adapter_reuse_rejects_unknown_checkpoint_source_commit(self) -> None:
        root = self._work_dir()
        adapter = root / "adapter"
        checkpoint = root / "full_checkpoint"
        adapter.mkdir(); checkpoint.mkdir()
        (adapter / "adapter_model.safetensors").write_bytes(b"weights")
        (adapter / "adapter_config.json").write_text("{}")
        (adapter / "adapter_identity.json").write_text(json.dumps({
                "base_model": "base", "selected_adapter": False,
        }))
        (adapter / "training_state.json").write_text(json.dumps({
                "base_model": "base", "task_registry_hash": "task", "field_registry_hash": "field",
        }))
        (checkpoint / "full_checkpoint_manifest.json").write_text(json.dumps({
                "selected_base_model": "base", "smoke_data_manifest_hash": "data",
                "training_config_hash": "config", "source_commit": "unknown",
        }))
        (root / "source_identity_manifest.json").write_text(json.dumps({"source_commit_sha": "other"}))
        result = verify_adapter_reuse(adapter, selected_base_model="base", config={}, train_manifest_hash="data", task_registry_hash="task", field_registry_hash="field", source_commit="expected")
        self.assertEqual(result["status"], "identity_mismatch")


if __name__ == "__main__":
    unittest.main()
