#!/usr/bin/env python3
"""Fail-fast T39 GPU admission check, run inside the immutable container."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any


MINIMUM_GPU_MEMORY_MIB = 90000


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise SystemExit(f"t39_gpu_preflight_output_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _nvidia_smi() -> dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.used,driver_version",
        "--format=csv,noheader,nounits",
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError("t39_gpu_preflight_requires_exactly_one_gpu")
    fields = [field.strip() for field in lines[0].split(",")]
    if len(fields) != 4:
        raise ValueError("t39_gpu_preflight_nvidia_smi_format_invalid")
    name, total_mib, used_mib, driver_version = fields
    return {
        "name": name,
        "memory_total_mib": int(total_mib),
        "memory_used_mib": int(used_mib),
        "driver_version": driver_version,
    }


def _torch() -> dict[str, Any]:
    import torch

    if not torch.cuda.is_available():
        raise ValueError("t39_cuda_required_but_unavailable")
    properties = torch.cuda.get_device_properties(0)
    total_mib = int(properties.total_memory // (1024 * 1024))
    if total_mib < MINIMUM_GPU_MEMORY_MIB:
        raise ValueError("t39_gpu_memory_below_minimum")
    # A tiny allocation/synchronisation verifies usable CUDA, not merely a
    # visible device name.  It is not model inference.
    probe = torch.ones((1,), device="cuda")
    torch.cuda.synchronize()
    del probe
    return {
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "gpu_name": torch.cuda.get_device_name(0),
        "gpu_memory_total_mib": total_mib,
        "gpu_compute_capability": list(torch.cuda.get_device_capability(0)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    nvidia = _nvidia_smi()
    if "Blackwell" not in nvidia["name"]:
        raise SystemExit("t39_gpu_preflight_non_blackwell_gpu")
    if nvidia["memory_total_mib"] < MINIMUM_GPU_MEMORY_MIB:
        raise SystemExit("t39_gpu_preflight_gpu_memory_below_minimum")
    if nvidia["memory_used_mib"] > 1000:
        raise SystemExit("t39_gpu_preflight_gpu_not_idle")
    payload = {
        "status": "T39_GPU_RUNTIME_PREFLIGHT_PASSED",
        "minimum_gpu_memory_mib": MINIMUM_GPU_MEMORY_MIB,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", "unknown"),
        "slurm_node": os.environ.get("SLURMD_NODENAME", "unknown"),
        "nvidia_smi": nvidia,
        "torch": _torch(),
    }
    _write_once(args.output.resolve(), payload)
    print(json.dumps({"status": payload["status"], "node": payload["slurm_node"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
