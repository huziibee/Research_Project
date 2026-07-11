"""T12 environment manifest validation."""

from __future__ import annotations

from typing import Any


def validate_environment_manifest(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if data.get("manifest_schema_version") != "1.0.0":
        errors.append("manifest_schema_version must be 1.0.0")

    if data.get("platform") != "wsl2_ubuntu":
        errors.append("platform must be wsl2_ubuntu for planned T12 environments")

    if data.get("python_target") != "3.11":
        errors.append("python_target must be 3.11")

    if data.get("package_manager") != "uv":
        errors.append("package_manager must be uv")

    if data.get("environment_status") != "planned_unverified":
        errors.append("environment_status must be planned_unverified in Slice 1")

    packages = data.get("packages")
    if not isinstance(packages, dict):
        errors.append("packages must be an object")
    else:
        for field in (
            "pytorch_version",
            "transformers_version",
            "peft_version",
            "trl_version",
            "bitsandbytes_version",
        ):
            if field not in packages:
                errors.append(f"packages.{field} missing")
            elif packages[field] is not None:
                errors.append(f"packages.{field} must be null until measured")

    if data.get("pytorch_cuda_build") is not None:
        errors.append("pytorch_cuda_build must be null until measured")

    if data.get("bitsandbytes_compatibility") is not None:
        errors.append("bitsandbytes_compatibility must be null until measured")

    if data.get("checkpoint_load_verified") is not False:
        errors.append("checkpoint_load_verified must be false in Slice 1")

    return errors
