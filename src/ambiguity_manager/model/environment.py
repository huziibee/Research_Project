"""T12 environment manifest validation."""

from __future__ import annotations

import re
from typing import Any

INFERENCE_ENV_REL = "configs/environments/historical/t12_inference_environment.json"
TRAINING_ENV_REL = "configs/environments/historical/t12_training_environment.json"
CLUSTER_INFERENCE_ENV_REL = "configs/environments/t12_cluster_inference.json"
CLUSTER_TRAINING_ENV_REL = "configs/environments/t12_cluster_training.json"

_VALID_STATUSES_SLICE1 = frozenset({"planned_unverified"})
_VALID_STATUSES_SLICE2 = frozenset(
    {"verified_compatible", "partially_verified", "blocked_incompatible"}
)
_ABSOLUTE_PATH_PATTERN = re.compile(r"^[A-Za-z]:[\\/]|^/home/|^/Users/|^\\\\")
_USERNAME_PATTERN = re.compile(r"\bhuzii\b", re.IGNORECASE)

_INFERENCE_PACKAGE_FIELDS = (
    "pytorch_version",
    "transformers_version",
    "tokenizers_version",
    "accelerate_version",
    "safetensors_version",
    "bitsandbytes_version",
)
_TRAINING_PACKAGE_FIELDS = _INFERENCE_PACKAGE_FIELDS + (
    "peft_version",
    "trl_version",
    "datasets_version",
)


def _scan_forbidden_identifiers(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, str):
        if _ABSOLUTE_PATH_PATTERN.search(value):
            errors.append(f"{path} contains absolute path")
        if _USERNAME_PATTERN.search(value):
            errors.append(f"{path} contains username")
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            _scan_forbidden_identifiers(nested, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _scan_forbidden_identifiers(nested, f"{path}[{index}]", errors)


def validate_environment_manifest(
    data: dict[str, Any],
    *,
    slice_number: int = 1,
) -> list[str]:
    errors: list[str] = []

    if data.get("manifest_schema_version") != "1.0.0":
        errors.append("manifest_schema_version must be 1.0.0")

    if data.get("platform") != "wsl2_ubuntu":
        errors.append("platform must be wsl2_ubuntu for planned T12 environments")

    if data.get("python_target") != "3.11":
        errors.append("python_target must be 3.11")

    if data.get("package_manager") != "uv":
        errors.append("package_manager must be uv")

    env_id = data.get("environment_id")
    if env_id not in {"t12-inference-wsl2", "t12-training-wsl2"}:
        errors.append("environment_id must be a known T12 WSL2 identifier")

    role = data.get("role")
    if role not in {"inference", "training"}:
        errors.append("role must be inference or training")

    status = data.get("environment_status")
    if slice_number == 1:
        if status not in _VALID_STATUSES_SLICE1:
            errors.append("environment_status must be planned_unverified in Slice 1")
    else:
        if status not in _VALID_STATUSES_SLICE2:
            errors.append("environment_status must be a Slice 2 verification status")

    packages = data.get("packages")
    if not isinstance(packages, dict):
        errors.append("packages must be an object")
    else:
        expected_fields = (
            _TRAINING_PACKAGE_FIELDS if role == "training" else _INFERENCE_PACKAGE_FIELDS
        )
        for field in expected_fields:
            if field not in packages:
                errors.append(f"packages.{field} missing")

        if slice_number == 1:
            for field in (
                "pytorch_version",
                "transformers_version",
                "peft_version",
                "trl_version",
                "bitsandbytes_version",
            ):
                if field in packages and packages[field] is not None:
                    errors.append(f"packages.{field} must be null until measured")
        elif status == "verified_compatible":
            for field in ("pytorch_version", "transformers_version", "tokenizers_version"):
                if not packages.get(field):
                    errors.append(
                        f"packages.{field} must be set for verified_compatible environments"
                    )
            if not packages.get("bitsandbytes_version"):
                errors.append("packages.bitsandbytes_version must be set for verified_compatible")

    if slice_number == 1:
        if data.get("pytorch_cuda_build") is not None:
            errors.append("pytorch_cuda_build must be null until measured")
        if data.get("bitsandbytes_compatibility") is not None:
            errors.append("bitsandbytes_compatibility must be null until measured")
    elif status == "verified_compatible":
        if not data.get("pytorch_cuda_build"):
            errors.append("pytorch_cuda_build required for verified_compatible")
        if not data.get("lockfile_relpath"):
            errors.append("lockfile_relpath required for verified_compatible")
        if not data.get("lockfile_sha256"):
            errors.append("lockfile_sha256 required for verified_compatible")
        if not data.get("requirements_input_relpath"):
            errors.append("requirements_input_relpath required for verified_compatible")
        if not data.get("requirements_input_sha256"):
            errors.append("requirements_input_sha256 required for verified_compatible")
        bnb_compat = data.get("bitsandbytes_compatibility")
        if bnb_compat != "cuda_operation_verified":
            errors.append(
                "bitsandbytes_compatibility must be cuda_operation_verified for verified_compatible"
            )
        for field in ("pytorch_version", "transformers_version", "tokenizers_version", "bitsandbytes_version"):
            if not packages.get(field):
                errors.append(
                    f"packages.{field} must be set for verified_compatible environments"
                )
    elif status == "partially_verified":
        if not data.get("pytorch_cuda_build"):
            errors.append("pytorch_cuda_build required for partially_verified")
        if not data.get("lockfile_relpath"):
            errors.append("lockfile_relpath required for partially_verified")
        if not data.get("lockfile_sha256"):
            errors.append("lockfile_sha256 required for partially_verified")
        if data.get("bitsandbytes_compatibility") is None:
            errors.append("bitsandbytes_compatibility must be recorded for partially_verified")
        for field in ("pytorch_version", "transformers_version", "tokenizers_version"):
            if not packages.get(field):
                errors.append(
                    f"packages.{field} must be set for partially_verified environments"
                )

    if data.get("checkpoint_load_verified") is not False:
        errors.append("checkpoint_load_verified must be false in Slice 2")

    if data.get("model_id") is not None:
        errors.append("model_id must remain null in Slice 2")
    if data.get("model_revision") is not None:
        errors.append("model_revision must remain null in Slice 2")

    _scan_forbidden_identifiers(data, "manifest", errors)
    return errors
