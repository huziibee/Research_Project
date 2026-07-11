"""T12 hardware evidence manifest validation."""

from __future__ import annotations

import re
from typing import Any

HARDWARE_MANIFEST_REL = "configs/model/evidence/t12_hardware_manifest.json"

_MEMORY_UNITS = frozenset({"KiB", "bytes", "MiB"})
_ABSOLUTE_PATH_PATTERN = re.compile(r"^[A-Za-z]:[\\/]|^/home/|^/Users/|^\\\\")
_USERNAME_PATTERN = re.compile(r"\bhuzii\b", re.IGNORECASE)
_UUID_PATTERN = re.compile(r"\buuid\b", re.IGNORECASE)


def normalise_memory_to_mib(raw_value: int, raw_unit: str) -> int:
    if raw_unit == "KiB":
        return raw_value // 1024
    if raw_unit == "bytes":
        return raw_value // (1024 * 1024)
    if raw_unit == "MiB":
        return int(raw_value)
    raise ValueError(f"unsupported memory unit: {raw_unit}")


def _validate_memory_field(field: dict[str, Any], path: str, errors: list[str]) -> None:
    required = {"raw_value", "raw_unit", "normalised_mib", "collection_source"}
    missing = required - set(field)
    if missing:
        errors.append(f"{path} missing fields: {sorted(missing)}")
        return
    raw_unit = field.get("raw_unit")
    if raw_unit not in _MEMORY_UNITS:
        errors.append(f"{path}.raw_unit invalid")
        return
    try:
        raw_value = int(field["raw_value"])
        expected = normalise_memory_to_mib(raw_value, raw_unit)
    except (TypeError, ValueError):
        errors.append(f"{path}.raw_value invalid")
        return
    if int(field["normalised_mib"]) != expected:
        errors.append(f"{path}.normalised_mib mismatch")


def _scan_forbidden_identifiers(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, str):
        if _ABSOLUTE_PATH_PATTERN.search(value):
            errors.append(f"{path} contains absolute path")
        if _USERNAME_PATTERN.search(value):
            errors.append(f"{path} contains username")
        if _UUID_PATTERN.search(value):
            errors.append(f"{path} contains gpu uuid reference")
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            _scan_forbidden_identifiers(nested, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _scan_forbidden_identifiers(nested, f"{path}[{index}]", errors)


def validate_hardware_manifest(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if data.get("manifest_schema_version") != "1.0.0":
        errors.append("manifest_schema_version must be 1.0.0")
    if data.get("ticket") != "T12":
        errors.append("ticket must be T12")

    for section in ("windows_host", "wsl2_ubuntu"):
        if section not in data:
            errors.append(f"missing section {section}")

    windows = data.get("windows_host", {})
    for key in (
        "driver_reported_cuda_version",
        "cuda_toolkit_nvcc_detected",
        "pytorch_cuda_build",
        "pytorch_cuda_available",
    ):
        if key not in windows:
            errors.append(f"windows_host missing {key}")

    if windows.get("pytorch_cuda_build") is not None or windows.get("pytorch_cuda_available") is not None:
        errors.append("windows_host must not claim installed PyTorch CUDA status in Slice 1")

    gpu = windows.get("gpu", {})
    for mem_field in ("vram_total", "vram_free", "vram_used"):
        if mem_field in gpu:
            _validate_memory_field(gpu[mem_field], f"windows_host.gpu.{mem_field}", errors)

    for mem_field in ("system_ram_total", "physical_memory_total"):
        if mem_field in windows:
            _validate_memory_field(windows[mem_field], f"windows_host.{mem_field}", errors)

    wsl = data.get("wsl2_ubuntu", {})
    wsl_gpu = wsl.get("gpu", {})
    for mem_field in ("vram_total", "vram_free", "vram_used"):
        if mem_field in wsl_gpu:
            _validate_memory_field(wsl_gpu[mem_field], f"wsl2_ubuntu.gpu.{mem_field}", errors)

    _scan_forbidden_identifiers(data, "manifest", errors)
    return errors
