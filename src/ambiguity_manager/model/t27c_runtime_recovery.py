"""CPU-safe contracts for bounded, observable T27C task inference.

This module deliberately has no model-stack imports.  The cluster runner uses
these small primitives around its existing Transformers/lm-format-enforcer
path; tests can exercise recovery mechanics without CUDA or a model snapshot.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import signal
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex


PREDICTION_TIMEOUT = "prediction_timeout"
TERMINAL_STATUSES = frozenset({"completed", PREDICTION_TIMEOUT, "failed", "cancelled"})


class RuntimeRecoveryError(RuntimeError):
    """Raised when recovery evidence is unsafe or cannot be resumed."""


class PredictionTimeout(RuntimeRecoveryError):
    """A single task call exceeded its frozen wall-clock bound."""


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Replace a JSON file atomically and durably."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            if os.name != "nt":
                os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


@dataclass
class Heartbeat:
    path: Path
    run_id: str
    total_task_calls: int
    latest_successful_output_time: str | None = None

    def update(self, **fields: Any) -> dict[str, Any]:
        payload = {
            "run_id": self.run_id,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pid": os.getpid(),
            "total_expected_task_calls": self.total_task_calls,
            "latest_successful_output_time": self.latest_successful_output_time,
        }
        payload.update(fields)
        if fields.get("status") == "completed":
            self.latest_successful_output_time = payload["timestamp_utc"]
            payload["latest_successful_output_time"] = self.latest_successful_output_time
        atomic_write_json(self.path, payload)
        return payload


def _journal_identity(entry: Mapping[str, Any]) -> tuple[str, str, str]:
    return (str(entry.get("mode")), str(entry.get("record_id")), str(entry.get("task_id")))


class PredictionJournal:
    """Append-only task-attempt journal with duplicate/corruption checks."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.entries: list[dict[str, Any]] = []
        self._identities: set[tuple[str, str, str]] = set()
        if path.exists():
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeRecoveryError(f"corrupt_journal_line:{line_number}") from exc
                if not isinstance(value, dict) or not _journal_identity(value)[0]:
                    raise RuntimeRecoveryError(f"invalid_journal_entry:{line_number}")
                identity = _journal_identity(value)
                if identity in self._identities:
                    raise RuntimeRecoveryError(f"duplicate_journal_entry:{identity}")
                if value.get("status") not in TERMINAL_STATUSES:
                    raise RuntimeRecoveryError(f"non_terminal_journal_entry:{line_number}")
                self.entries.append(value)
                self._identities.add(identity)

    def append(self, entry: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(entry)
        identity = _journal_identity(value)
        if not identity[0] or not identity[1] or not identity[2]:
            raise RuntimeRecoveryError("journal_identity_required")
        if value.get("status") not in TERMINAL_STATUSES:
            raise RuntimeRecoveryError("journal_status_not_terminal")
        if identity in self._identities:
            raise RuntimeRecoveryError(f"duplicate_journal_entry:{identity}")
        line = json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            if os.name != "nt":
                os.fsync(handle.fileno())
        self.entries.append(value)
        self._identities.add(identity)
        return value

    def completed(self, *, mode: str, record_id: str, task_id: str) -> dict[str, Any] | None:
        identity = (mode, record_id, task_id)
        for entry in self.entries:
            if _journal_identity(entry) == identity:
                if entry.get("status") == "completed" and entry.get("validation_status") == "valid":
                    return entry
                return None
        return None


def expected_task_calls(
    records: Iterable[Mapping[str, Any]],
    matrix: Mapping[str, Any],
    task_ids_for_record: Callable[[Mapping[str, Any]], Sequence[str]],
    modes: Sequence[str] = ("base", "adapter"),
) -> list[dict[str, str]]:
    calls: list[dict[str, str]] = []
    for record in records:
        record_id = str(record["id"])
        for mode in modes:
            for task_id in task_ids_for_record(record):
                calls.append({"mode": mode, "record_id": record_id, "task_id": str(task_id)})
    return calls


def freeze_task_timeouts(
    timings_by_task: Mapping[str, Sequence[float]],
    task_registry: Mapping[str, Any],
    *,
    declared_minimum_seconds: float = 60.0,
    multiplier: float = 3.0,
) -> dict[str, int]:
    """Freeze p95-derived bounds from diagnostic timings only."""
    if multiplier <= 0 or declared_minimum_seconds <= 0:
        raise RuntimeRecoveryError("invalid_timeout_rule")
    result: dict[str, int] = {}
    for task in task_registry.get("tasks") or []:
        task_id = str(task["task_id"])
        timings = [float(x) for x in timings_by_task.get(task_id, ()) if float(x) >= 0]
        if not timings:
            raise RuntimeRecoveryError(f"missing_diagnostic_timing:{task_id}")
        ordered = sorted(timings)
        index = max(0, min(len(ordered) - 1, int((len(ordered) * 0.95 + 0.999999)) - 1))
        result[task_id] = max(int(declared_minimum_seconds), int(math.ceil(ordered[index] * multiplier)))
    return result


def run_bounded(call: Callable[[], Any], timeout_seconds: float) -> Any:
    """Run one call with a hard bound where the platform permits it."""
    if timeout_seconds <= 0:
        raise RuntimeRecoveryError("timeout_must_be_positive")
    if not hasattr(signal, "SIGALRM"):
        # Windows has no process signal timer.  A daemon worker still gives the
        # caller a bounded decision; cluster execution uses the POSIX branch.
        state: dict[str, Any] = {}

        def _worker() -> None:
            try:
                state["value"] = call()
            except BaseException as exc:  # noqa: BLE001
                state["error"] = exc

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        thread.join(timeout_seconds)
        if thread.is_alive():
            raise PredictionTimeout(PREDICTION_TIMEOUT)
        if "error" in state:
            raise state["error"]
        return state.get("value")

    def _alarm(_signum: int, _frame: Any) -> None:
        raise PredictionTimeout(PREDICTION_TIMEOUT)

    prior_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return call()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prior_handler)


def generated_continuation(input_ids: Sequence[int], output_ids: Sequence[int]) -> list[int]:
    """Return only newly generated IDs; reject output shorter than the prompt."""
    if len(output_ids) < len(input_ids) or list(output_ids[: len(input_ids)]) != list(input_ids):
        raise RuntimeRecoveryError("generation_prompt_echo_or_prefix_mismatch")
    return list(output_ids[len(input_ids) :])


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_adapter_reuse(
    adapter_dir: Path,
    *,
    selected_base_model: str,
    config: Mapping[str, Any],
    train_manifest_hash: str,
    task_registry_hash: str,
    field_registry_hash: str,
    source_commit: str,
) -> dict[str, Any]:
    """Verify a technical adapter without selecting it for official use."""
    required = ["adapter_model.safetensors", "adapter_config.json", "adapter_identity.json", "training_state.json"]
    missing = [name for name in required if not (adapter_dir / name).is_file()]
    manifest_path = adapter_dir.parent / "full_checkpoint" / "full_checkpoint_manifest.json"
    source_path = adapter_dir.parent / "source_identity_manifest.json"
    if missing or not manifest_path.is_file() or not source_path.is_file():
        return {"status": "incomplete", "missing": missing}
    try:
        identity = json.loads((adapter_dir / "adapter_identity.json").read_text(encoding="utf-8"))
        state = json.loads((adapter_dir / "training_state.json").read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source = json.loads(source_path.read_text(encoding="utf-8"))
        expected_config_hash = sha256_hex(canonical_json_bytes(dict(config)))
        checks = {
            "base_identity": identity.get("base_model") == selected_base_model and state.get("base_model") == selected_base_model and manifest.get("selected_base_model") == selected_base_model,
            "task_registry_hash": state.get("task_registry_hash") == task_registry_hash,
            "field_registry_hash": state.get("field_registry_hash") == field_registry_hash,
            "training_manifest_hash": manifest.get("smoke_data_manifest_hash") == train_manifest_hash,
            "config_hash": manifest.get("training_config_hash") == expected_config_hash,
            "source_commit": source.get("source_commit_sha") == source_commit,
            "adapter_hash": bool(identity.get("safetensors_sha256")) and _file_hash(adapter_dir / "adapter_model.safetensors") == identity.get("safetensors_sha256"),
            "not_selected": identity.get("selected_adapter") is False,
        }
        status = "reusable" if all(checks.values()) else "identity_mismatch"
        return {
            "status": status,
            "checks": checks,
            "adapter_sha256": _file_hash(adapter_dir / "adapter_model.safetensors"),
            "adapter_bytes": (adapter_dir / "adapter_model.safetensors").stat().st_size,
        }
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return {"status": "corrupt", "detail": f"{type(exc).__name__}:{exc}"}
