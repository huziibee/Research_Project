#!/usr/bin/env python3
"""T12 deterministic WSL2 environment probe — package/CUDA verification only."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROBE_SCHEMA_VERSION = "1.0.0"
MATRIX_DIM = 32
TOLERANCE = 1e-4


def _repo_root() -> Path:
    start = Path(__file__).resolve().parent
    for directory in [start, *start.parents]:
        if (directory / "pyproject.toml").is_file():
            return directory
    raise FileNotFoundError("could not locate repository root")


def _uv_version() -> str | None:
    try:
        completed = subprocess.run(
            ["uv", "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def _import_with_status(module_name: str) -> tuple[dict[str, Any], Any | None]:
    try:
        module = __import__(module_name)
        version = getattr(module, "__version__", None)
        return {"status": "ok", "version": version}, module
    except Exception as exc:  # noqa: BLE001 - probe must record all import failures
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, None


def _cuda_smoke_test(torch_mod: Any) -> dict[str, Any]:
    if not torch_mod.cuda.is_available():
        return {"status": "failed", "reason": "torch.cuda.is_available() is false"}

    torch_mod.cuda.reset_peak_memory_stats()
    cpu_a = torch_mod.randn(MATRIX_DIM, MATRIX_DIM, dtype=torch_mod.float32)
    cpu_b = torch_mod.randn(MATRIX_DIM, MATRIX_DIM, dtype=torch_mod.float32)
    expected = cpu_a @ cpu_b

    device = torch_mod.device("cuda:0")
    gpu_a = cpu_a.to(device)
    gpu_b = cpu_b.to(device)
    result = gpu_a @ gpu_b
    torch_mod.cuda.synchronize()
    max_abs_diff = (result.cpu() - expected).abs().max().item()

    peak_allocated = torch_mod.cuda.max_memory_allocated() / (1024 * 1024)
    peak_reserved = torch_mod.cuda.max_memory_reserved() / (1024 * 1024)

    del gpu_a, gpu_b, result
    torch_mod.cuda.empty_cache()
    torch_mod.cuda.synchronize()

    status = "passed" if max_abs_diff <= TOLERANCE else "failed"
    return {
        "status": status,
        "max_abs_diff": max_abs_diff,
        "tolerance": TOLERANCE,
        "peak_allocated_mib": round(peak_allocated, 3),
        "peak_reserved_mib": round(peak_reserved, 3),
    }


def _bitsandbytes_probe(torch_mod: Any, bnb_mod: Any | None) -> dict[str, Any]:
    if bnb_mod is None:
        return {"status": "failed", "reason": "bitsandbytes import failed"}
    if not torch_mod.cuda.is_available():
        return {"status": "unsupported", "reason": "CUDA unavailable"}

    try:
        parameter = torch_mod.nn.Parameter(
            torch_mod.randn(16, 16, device="cuda", dtype=torch_mod.float32)
        )
        optim_cls = getattr(bnb_mod, "optim", None)
        if optim_cls is None or not hasattr(optim_cls, "Adam8bit"):
            return {"status": "import_only", "reason": "Adam8bit optimizer unavailable"}
        optimizer = optim_cls.Adam8bit([parameter])
        loss = parameter.pow(2).mean()
        loss.backward()
        optimizer.step()
        torch_mod.cuda.synchronize()
        del parameter, optimizer, loss
        torch_mod.cuda.empty_cache()
        version = getattr(bnb_mod, "__version__", None)
        return {"status": "cuda_operation_verified", "version": version}
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}


def _gpu_memory_mib(torch_mod: Any) -> tuple[int | None, int | None]:
    if not torch_mod.cuda.is_available():
        return None, None
    free_bytes, total_bytes = torch_mod.cuda.mem_get_info()
    return int(total_bytes / (1024 * 1024)), int(free_bytes / (1024 * 1024))


def build_probe(environment_id: str, role: str) -> dict[str, Any]:
    import_failures: list[str] = []
    imports: dict[str, dict[str, Any]] = {}

    torch_info, torch_mod = _import_with_status("torch")
    imports["torch"] = {k: v for k, v in torch_info.items() if k != "version"}
    if torch_info["status"] != "ok":
        import_failures.append("torch")
        torch_mod = None

    for package in ("transformers", "tokenizers", "safetensors", "accelerate", "bitsandbytes"):
        info, _ = _import_with_status(package)
        imports[package] = {k: v for k, v in info.items() if k != "version"}
        if info["status"] != "ok":
            import_failures.append(package)

    training_versions: dict[str, str | None] = {}
    if role == "training":
        for package in ("peft", "trl", "datasets"):
            info, _ = _import_with_status(package)
            imports[package] = {k: v for k, v in info.items() if k != "version"}
            if info["status"] != "ok":
                import_failures.append(package)

    bnb_mod = None
    if imports.get("bitsandbytes", {}).get("status") == "ok":
        _, bnb_mod = _import_with_status("bitsandbytes")

    cuda_available = bool(torch_mod and torch_mod.cuda.is_available())
    device_count = int(torch_mod.cuda.device_count()) if cuda_available and torch_mod else 0
    gpu_name = None
    compute_capability = None
    bf16_supported = False
    vram_total_mib = None
    vram_free_mib = None

    if cuda_available and torch_mod:
        gpu_name = torch_mod.cuda.get_device_name(0)
        major, minor = torch_mod.cuda.get_device_capability(0)
        compute_capability = f"{major}.{minor}"
        bf16_supported = bool(torch_mod.cuda.is_bf16_supported())
        vram_total_mib, vram_free_mib = _gpu_memory_mib(torch_mod)

    cuda_computation = (
        _cuda_smoke_test(torch_mod)
        if torch_mod is not None
        else {"status": "failed", "reason": "torch unavailable"}
    )
    bitsandbytes_result = (
        _bitsandbytes_probe(torch_mod, bnb_mod)
        if torch_mod is not None
        else {"status": "failed", "reason": "torch unavailable"}
    )

    def _version(package: str) -> str | None:
        info = imports.get(package, {})
        if info.get("status") != "ok":
            return None
        _, module = _import_with_status(package)
        return getattr(module, "__version__", None) if module else None

    if role == "training":
        training_versions = {
            "peft_version": _version("peft"),
            "trl_version": _version("trl"),
            "datasets_version": _version("datasets"),
        }

    return {
        "probe_schema_version": PROBE_SCHEMA_VERSION,
        "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "environment_id": environment_id,
        "role": role,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "os_name": platform.system(),
        "os_architecture": platform.machine(),
        "uv_version": _uv_version(),
        "torch_version": _version("torch"),
        "torch_cuda_build": getattr(torch_mod.version, "cuda", None) if torch_mod else None,
        "torch_cuda_is_available": cuda_available,
        "cuda_device_count": device_count,
        "gpu_name": gpu_name,
        "compute_capability": compute_capability,
        "vram_total_mib": vram_total_mib,
        "vram_free_mib": vram_free_mib,
        "bf16_supported": bf16_supported,
        "transformers_version": _version("transformers"),
        "tokenizers_version": _version("tokenizers"),
        "safetensors_version": _version("safetensors"),
        "accelerate_version": _version("accelerate"),
        "bitsandbytes_version": _version("bitsandbytes"),
        **training_versions,
        "bitsandbytes_status": bitsandbytes_result["status"],
        "bitsandbytes_details": bitsandbytes_result,
        "cuda_computation": cuda_computation,
        "imports": imports,
        "import_failures": import_failures,
        "no_model_download": True,
        "no_absolute_paths": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--environment-id",
        required=True,
        choices=["t12-inference-wsl2", "t12-training-wsl2"],
    )
    parser.add_argument(
        "--role",
        required=True,
        choices=["inference", "training"],
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for raw probe JSON (defaults to outputs/environment_probes).",
    )
    args = parser.parse_args()

    probe = build_probe(args.environment_id, args.role)
    payload = json.dumps(probe, indent=2, sort_keys=True)
    print(payload)

    output_dir = args.output_dir or (_repo_root() / "outputs" / "environment_probes")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{args.environment_id}.json"
    output_path.write_text(payload + "\n", encoding="utf-8")
    return 0 if probe["cuda_computation"].get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
