"""T12 Slice 2 environment compatibility evidence validation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ambiguity_manager.governance.hashing import sha256_hex

EVIDENCE_REL = "configs/model/evidence/historical/t12_environment_compatibility.json"
INFERENCE_REQ_REL = "requirements/historical/t12-wsl2/t12-inference.in"
TRAINING_REQ_REL = "requirements/historical/t12-wsl2/t12-training.in"
INFERENCE_LOCK_REL = "requirements/historical/t12-wsl2/t12-inference-wsl2.lock"
TRAINING_LOCK_REL = "requirements/historical/t12-wsl2/t12-training-wsl2.lock"

_ENVIRONMENT_IDS = frozenset({"t12-inference-wsl2", "t12-training-wsl2"})
_VALID_OVERALL_STATUSES = frozenset(
    {"verified_compatible", "partially_verified", "blocked_incompatible"}
)
_VALID_BITSANDBYTES_STATUSES = frozenset(
    {"cuda_operation_verified", "import_only", "unsupported", "failed"}
)
_INFERENCE_IMPORTS = frozenset(
    {"torch", "transformers", "tokenizers", "safetensors", "accelerate", "bitsandbytes"}
)
_TRAINING_IMPORTS = _INFERENCE_IMPORTS | frozenset({"peft", "trl", "datasets"})
_ABSOLUTE_PATH_PATTERN = re.compile(r"^[A-Za-z]:[\\/]|^/home/|^/Users/|^\\\\")
_USERNAME_PATTERN = re.compile(r"\bhuzii\b", re.IGNORECASE)


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


def parse_probe_result(data: dict[str, Any]) -> dict[str, Any]:
    """Normalise a raw environment probe payload for evidence ingestion."""
    required = (
        "probe_schema_version",
        "environment_id",
        "role",
        "python_version",
        "torch_version",
        "torch_cuda_build",
        "torch_cuda_is_available",
        "cuda_computation",
        "imports",
        "no_model_download",
        "no_absolute_paths",
    )
    missing = [field for field in required if field not in data]
    if missing:
        raise ValueError(f"probe missing fields: {missing}")
    if data["environment_id"] not in _ENVIRONMENT_IDS:
        raise ValueError(f"unknown environment_id: {data['environment_id']}")
    return data


def _validate_imports(imports: Any, role: str, prefix: str, errors: list[str]) -> None:
    if not isinstance(imports, dict):
        errors.append(f"{prefix}.imports must be an object")
        return
    expected = _TRAINING_IMPORTS if role == "training" else _INFERENCE_IMPORTS
    for package in expected:
        entry = imports.get(package)
        if not isinstance(entry, dict):
            errors.append(f"{prefix}.imports.{package} missing")
            continue
        if entry.get("status") != "ok":
            errors.append(f"{prefix}.imports.{package} must be ok for verified_compatible")


def _validate_environment_block(
    block: Any,
    repo_root: Path,
    errors: list[str],
) -> None:
    if not isinstance(block, dict):
        errors.append("environment block must be an object")
        return

    env_id = block.get("environment_id")
    prefix = f"environments.{env_id}"
    if env_id not in _ENVIRONMENT_IDS:
        errors.append(f"{prefix} invalid environment_id")
        return

    role = block.get("role")
    if role not in {"inference", "training"}:
        errors.append(f"{prefix}.role invalid")

    overall = block.get("overall_status")
    if overall not in _VALID_OVERALL_STATUSES:
        errors.append(f"{prefix}.overall_status invalid")

    if block.get("checkpoint_load_verified") is not False:
        errors.append(f"{prefix}.checkpoint_load_verified must be false in Slice 2")

    lock_rel = block.get("lockfile_relpath")
    lock_hash = block.get("lockfile_sha256")
    req_rel = block.get("requirements_input_relpath")
    req_hash = block.get("requirements_input_sha256")

    if overall == "verified_compatible":
        if not lock_rel:
            errors.append(f"{prefix}.lockfile_relpath required for verified_compatible")
        if not lock_hash:
            errors.append(f"{prefix}.lockfile_sha256 required for verified_compatible")
        if not req_rel:
            errors.append(f"{prefix}.requirements_input_relpath required for verified_compatible")
        if not req_hash:
            errors.append(f"{prefix}.requirements_input_sha256 required for verified_compatible")
        if block.get("cuda_compatibility") != "passed":
            errors.append(f"{prefix}.cuda_compatibility must be passed for verified_compatible")
        if block.get("gpu_computation") != "passed":
            errors.append(f"{prefix}.gpu_computation must be passed for verified_compatible")
        _validate_imports(block.get("imports"), role or "inference", prefix, errors)

        bnb_status = block.get("bitsandbytes_status")
        if bnb_status not in _VALID_BITSANDBYTES_STATUSES:
            errors.append(f"{prefix}.bitsandbytes_status invalid")
        elif bnb_status != "cuda_operation_verified":
            errors.append(
                f"{prefix}.bitsandbytes_status must be cuda_operation_verified for verified_compatible"
            )

        packages = block.get("packages")
        if not isinstance(packages, dict):
            errors.append(f"{prefix}.packages must be an object")
        else:
            for field in (
                "pytorch_version",
                "transformers_version",
                "tokenizers_version",
                "bitsandbytes_version",
            ):
                if not packages.get(field):
                    errors.append(f"{prefix}.packages.{field} required for verified_compatible")

    elif overall == "partially_verified":
        if block.get("cuda_compatibility") != "passed":
            errors.append(f"{prefix}.cuda_compatibility must be passed for partially_verified")
        if block.get("gpu_computation") != "passed":
            errors.append(f"{prefix}.gpu_computation must be passed for partially_verified")
        bnb_status = block.get("bitsandbytes_status")
        if bnb_status not in _VALID_BITSANDBYTES_STATUSES:
            errors.append(f"{prefix}.bitsandbytes_status invalid")

    if lock_rel and lock_hash:
        lock_path = repo_root / lock_rel
        if not lock_path.is_file():
            errors.append(f"{prefix}.lockfile_relpath missing on disk: {lock_rel}")
        elif sha256_hex(lock_path.read_bytes()) != lock_hash:
            errors.append(f"{prefix}.lockfile_sha256 mismatch")

    if req_rel and req_hash:
        req_path = repo_root / req_rel
        if not req_path.is_file():
            errors.append(f"{prefix}.requirements_input_relpath missing on disk: {req_rel}")
        elif sha256_hex(req_path.read_bytes()) != req_hash:
            errors.append(f"{prefix}.requirements_input_sha256 mismatch")


def validate_environment_evidence(data: dict[str, Any], *, repo_root: Path) -> list[str]:
    errors: list[str] = []

    if data.get("manifest_schema_version") != "1.0.0":
        errors.append("manifest_schema_version must be 1.0.0")
    if data.get("ticket") != "T12":
        errors.append("ticket must be T12")
    if data.get("slice") != 2:
        errors.append("slice must be 2")
    if data.get("no_model_download") is not True:
        errors.append("no_model_download must be true")
    if data.get("no_absolute_paths") is not True:
        errors.append("no_absolute_paths must be true")

    environments = data.get("environments")
    if not isinstance(environments, dict):
        errors.append("environments must be an object")
    else:
        for env_id in _ENVIRONMENT_IDS:
            if env_id not in environments:
                errors.append(f"missing environments.{env_id}")
        for env_id, block in environments.items():
            _validate_environment_block(block, repo_root, errors)

    matrix = data.get("compatibility_matrix")
    if not isinstance(matrix, list) or not matrix:
        errors.append("compatibility_matrix must be a non-empty list")

    os_deps = data.get("os_compiler_dependencies")
    if not isinstance(os_deps, dict):
        errors.append("os_compiler_dependencies must be an object")
    else:
        if os_deps.get("tracked_in_python_lockfiles") is not False:
            errors.append("os_compiler_dependencies.tracked_in_python_lockfiles must be false")
        packages = os_deps.get("packages")
        if not isinstance(packages, list) or not packages:
            errors.append("os_compiler_dependencies.packages must be a non-empty list")
        for tool in ("cc", "cxx"):
            if not os_deps.get(tool):
                errors.append(f"os_compiler_dependencies.{tool} required")

    _scan_forbidden_identifiers(data, "evidence", errors)
    return errors
