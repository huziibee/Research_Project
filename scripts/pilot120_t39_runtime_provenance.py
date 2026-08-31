#!/usr/bin/env python3
"""Capture immutable runtime evidence for one frozen T39 GPU component."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any


def _version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise SystemExit(f"t39_runtime_output_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _torch_payload() -> dict[str, Any]:
    try:
        import torch

        cuda_available = bool(torch.cuda.is_available())
        return {
            "version": getattr(torch, "__version__", None),
            "cuda_version": getattr(torch.version, "cuda", None),
            "cuda_available": cuda_available,
            "gpu_name": torch.cuda.get_device_name(0) if cuda_available else None,
        }
    except Exception as exc:  # provenance must explain an unavailable import, not hide it
        return {"status": "NOT_COMPUTED", "reason": f"torch_probe_failed:{type(exc).__name__}:{exc}"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--component", choices=("direct_base", "selected_adapter", "manager_bundle"), required=True)
    parser.add_argument("--replicate-id", required=True)
    args = parser.parse_args()
    payload = {
        "status": "T39_RUNTIME_PROVENANCE_CAPTURED",
        "component": args.component,
        "replicate_id": args.replicate_id,
        "slurm": {
            "job_id": os.environ.get("T39_SLURM_JOB_ID", "unknown"),
            "node": os.environ.get("T39_SLURMD_NODENAME", "unknown"),
            "cluster": os.environ.get("SLURM_CLUSTER_NAME", "unknown"),
        },
        "code": {"commit": os.environ.get("T39_CODE_COMMIT", "unknown"), "root": os.environ.get("T39_CODE_ROOT", "unknown")},
        "container": {
            "path": os.environ.get("T39_CONTAINER", "unknown"),
            "sha256": os.environ.get("T39_CONTAINER_SHA256", "unknown"),
        },
        "runtime": {
            "python": sys.version,
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "packages": {name: _version(name) for name in ("torch", "transformers", "peft", "accelerate", "bitsandbytes")},
            "torch": _torch_payload(),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", "unknown"),
        },
    }
    _write_once(args.output.resolve(), payload)
    print(json.dumps({"status": payload["status"], "component": args.component, "replicate_id": args.replicate_id}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
