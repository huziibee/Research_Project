"""Full training checkpoint / resume contract for task-aligned QLoRA (T27).

A checkpoint preserves adapter weights plus optimiser, scheduler, scaler,
global step, data position, RNG states, and identity hashes. Adapter-only
reload is tracked separately and is never treated as a full resume.
"""

from __future__ import annotations

import json
import pickle
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ambiguity_manager.governance.hashing import sha256_hex

CHECKPOINT_MANIFEST_NAME = "full_checkpoint_manifest.json"
CHECKPOINT_BLOB_NAME = "full_training_state.pt"
ADAPTER_SUBDIR = "adapter"


class CheckpointError(RuntimeError):
    """Raised when checkpoint save/resume fails the full contract."""


@dataclass(frozen=True)
class ResumeComponentResult:
    adapter_reload_ok: bool
    optimiser_restore_ok: bool
    scheduler_restore_ok: bool
    rng_restore_ok: bool
    data_position_restore_ok: bool

    @property
    def full_resume_ok(self) -> bool:
        return all(
            (
                self.adapter_reload_ok,
                self.optimiser_restore_ok,
                self.scheduler_restore_ok,
                self.rng_restore_ok,
                self.data_position_restore_ok,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_reload_ok": self.adapter_reload_ok,
            "optimiser_restore_ok": self.optimiser_restore_ok,
            "scheduler_restore_ok": self.scheduler_restore_ok,
            "rng_restore_ok": self.rng_restore_ok,
            "data_position_restore_ok": self.data_position_restore_ok,
            "full_resume_ok": self.full_resume_ok,
        }


def _sha256_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(dict(payload), indent=2, sort_keys=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def capture_rng_state() -> dict[str, Any]:
    state: dict[str, Any] = {
        "python": random.getstate(),
    }
    try:
        import numpy as np

        state["numpy"] = np.random.get_state()
    except Exception:  # noqa: BLE001
        state["numpy"] = None
    try:
        import torch

        state["torch_cpu"] = torch.random.get_rng_state()
        if torch.cuda.is_available():
            state["torch_cuda"] = torch.cuda.get_rng_state_all()
        else:
            state["torch_cuda"] = None
    except Exception:  # noqa: BLE001
        state["torch_cpu"] = None
        state["torch_cuda"] = None
    return state


def restore_rng_state(state: Mapping[str, Any]) -> bool:
    try:
        random.setstate(state["python"])
        if state.get("numpy") is not None:
            import numpy as np

            np.random.set_state(state["numpy"])
        if state.get("torch_cpu") is not None:
            import torch

            torch.random.set_rng_state(state["torch_cpu"])
            if state.get("torch_cuda") is not None and torch.cuda.is_available():
                torch.cuda.set_rng_state_all(state["torch_cuda"])
        return True
    except Exception as exc:  # noqa: BLE001
        raise CheckpointError(f"rng_restore_failed:{exc}") from exc


def build_checkpoint_payload(
    *,
    adapter_dir: Path,
    optimizer: Any,
    scheduler: Any | None,
    scaler: Any | None,
    global_step: int,
    epoch: int,
    data_position: int,
    consumed_example_ids: Sequence[str],
    training_config_hash: str,
    smoke_data_manifest_hash: str,
    selected_base_model: str,
    environment_identity: str,
    source_commit: str,
) -> dict[str, Any]:
    return {
        "optimizer": optimizer.state_dict(),
        "scheduler": None if scheduler is None else scheduler.state_dict(),
        "scaler": None if scaler is None else scaler.state_dict(),
        "global_step": int(global_step),
        "epoch": int(epoch),
        "data_position": int(data_position),
        "consumed_example_ids": list(consumed_example_ids),
        "rng": capture_rng_state(),
        "training_config_hash": training_config_hash,
        "smoke_data_manifest_hash": smoke_data_manifest_hash,
        "selected_base_model": selected_base_model,
        "environment_identity": environment_identity,
        "source_commit": source_commit,
        "adapter_dir_name": ADAPTER_SUBDIR,
    }


def save_full_checkpoint(
    checkpoint_dir: Path,
    *,
    payload: Mapping[str, Any],
    adapter_files_present: bool,
) -> dict[str, Any]:
    if not adapter_files_present:
        raise CheckpointError("adapter_weights_missing_for_checkpoint")
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    blob_path = checkpoint_dir / CHECKPOINT_BLOB_NAME
    # Prefer torch.save when available; fall back to pickle for CPU-only tests.
    try:
        import torch

        torch.save(dict(payload), blob_path)
    except Exception:
        blob_path.write_bytes(pickle.dumps(dict(payload), protocol=4))

    manifest = {
        "schema_version": "1.0.0",
        "checkpoint_blob": CHECKPOINT_BLOB_NAME,
        "checkpoint_blob_sha256": _sha256_file(blob_path),
        "checkpoint_blob_bytes": blob_path.stat().st_size,
        "global_step": payload["global_step"],
        "data_position": payload["data_position"],
        "selected_base_model": payload["selected_base_model"],
        "training_config_hash": payload["training_config_hash"],
        "smoke_data_manifest_hash": payload["smoke_data_manifest_hash"],
        "environment_identity": payload["environment_identity"],
        "source_commit": payload["source_commit"],
        "contains": [
            "adapter_weights_reference",
            "optimizer",
            "scheduler",
            "scaler",
            "global_step",
            "epoch",
            "data_position",
            "consumed_example_ids",
            "python_rng",
            "numpy_rng",
            "torch_cpu_rng",
            "torch_cuda_rng",
            "training_config_hash",
            "smoke_data_manifest_hash",
            "selected_base_model",
            "environment_identity",
            "source_commit",
        ],
    }
    _atomic_write_json(checkpoint_dir / CHECKPOINT_MANIFEST_NAME, manifest)
    return manifest


def load_full_checkpoint_blob(checkpoint_dir: Path) -> dict[str, Any]:
    blob_path = checkpoint_dir / CHECKPOINT_BLOB_NAME
    manifest_path = checkpoint_dir / CHECKPOINT_MANIFEST_NAME
    if not blob_path.is_file() or not manifest_path.is_file():
        raise CheckpointError("checkpoint_incomplete")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = _sha256_file(blob_path)
    if actual != manifest.get("checkpoint_blob_sha256"):
        raise CheckpointError("checkpoint_blob_hash_mismatch")
    try:
        import torch

        payload = torch.load(blob_path, map_location="cpu", weights_only=False)
    except Exception:
        payload = pickle.loads(blob_path.read_bytes())
    if not isinstance(payload, dict):
        raise CheckpointError("checkpoint_payload_not_dict")
    return payload


def assert_resume_identities(
    payload: Mapping[str, Any],
    *,
    selected_base_model: str,
    training_config_hash: str,
    smoke_data_manifest_hash: str,
    environment_identity: str,
) -> None:
    if payload.get("selected_base_model") != selected_base_model:
        raise CheckpointError("resume_blocked_base_identity_mismatch")
    if payload.get("training_config_hash") != training_config_hash:
        raise CheckpointError("resume_blocked_config_hash_mismatch")
    if payload.get("smoke_data_manifest_hash") != smoke_data_manifest_hash:
        raise CheckpointError("resume_blocked_data_manifest_mismatch")
    if payload.get("environment_identity") != environment_identity:
        raise CheckpointError("resume_blocked_environment_identity_mismatch")


def evaluate_resume_components(
    *,
    adapter_reload_ok: bool,
    optimiser_restore_ok: bool,
    scheduler_restore_ok: bool,
    rng_restore_ok: bool,
    data_position_restore_ok: bool,
) -> ResumeComponentResult:
    result = ResumeComponentResult(
        adapter_reload_ok=adapter_reload_ok,
        optimiser_restore_ok=optimiser_restore_ok,
        scheduler_restore_ok=scheduler_restore_ok,
        rng_restore_ok=rng_restore_ok,
        data_position_restore_ok=data_position_restore_ok,
    )
    if not result.full_resume_ok:
        # Callers decide whether to raise; returning the structured booleans is required.
        pass
    return result
