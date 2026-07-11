"""Path sanitisation for generic T12 cluster configuration."""

from __future__ import annotations

import re
from typing import Any

_FORBIDDEN_USERNAMES = re.compile(r"\b(huzii|huziiee|mbangie)\b", re.IGNORECASE)
_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]|\\\\")
_WSL_MOUNT = re.compile(r"^/mnt/[a-zA-Z]/")
_HOME_MSCLUSTER = re.compile(r"/home-mscluster/", re.IGNORECASE)
_CREDENTIAL_PATTERN = re.compile(
    r"(token|password|secret|api[_-]?key)\s*[:=]",
    re.IGNORECASE,
)
_ENV_VAR = re.compile(r"\$\{[A-Z0-9_]+\}")
_ALLOWED_LITERALS = frozenset(
    {
        "/var/tmp/${USER}-apptainer-${SLURM_JOB_ID}",
        "${HOME}",
        "${T12_CLUSTER_ROOT}",
        "${T12_HF_CACHE}",
        "${T12_HF_CACHE}/hub",
        "${T12_CONTAINER_SIF}",
    }
)
_SAFE_SUFFIX = re.compile(r"^(/[A-Za-z0-9_.${}-]+)*$")


def validate_path_template(value: str) -> list[str]:
    if value in _ALLOWED_LITERALS:
        return []
    if _ENV_VAR.fullmatch(value):
        return []

    for prefix in ("${T12_HF_CACHE}", "${T12_CLUSTER_ROOT}", "${T12_CONTAINER_SIF}"):
        if value.startswith(prefix):
            suffix = value[len(prefix) :]
            if suffix == "" or _SAFE_SUFFIX.fullmatch(suffix):
                return []

    errors: list[str] = []
    if _WINDOWS_PATH.search(value):
        errors.append("windows path forbidden")
    if _WSL_MOUNT.search(value):
        errors.append("wsl mount path forbidden")
    if _HOME_MSCLUSTER.search(value):
        errors.append("personal cluster home path forbidden")
    if _FORBIDDEN_USERNAMES.search(value):
        errors.append("personal username forbidden")
    if _CREDENTIAL_PATTERN.search(value):
        errors.append("embedded credential forbidden")

    stripped = _ENV_VAR.sub("", value)
    if stripped and _FORBIDDEN_USERNAMES.search(stripped):
        errors.append("personal username forbidden")
    return errors


def scan_forbidden_paths(value: Any, *, path: str = "root") -> list[str]:
    errors: list[str] = []
    if isinstance(value, str):
        for msg in validate_path_template(value):
            errors.append(f"{path}: {msg}")
        return errors
    if isinstance(value, dict):
        for key, nested in value.items():
            errors.extend(scan_forbidden_paths(nested, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            errors.extend(scan_forbidden_paths(nested, path=f"{path}[{index}]"))
    return errors
