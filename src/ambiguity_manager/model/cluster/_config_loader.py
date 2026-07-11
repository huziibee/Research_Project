"""Load T12 cluster configuration artefacts (stdlib only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.cluster.identities import IMMUTABLE_SELECTION_REL, load_immutable_selection
from ambiguity_manager.model.cluster.manifest_schemas import (
    CLUSTER_EXECUTION_POLICY_REL,
    CLUSTER_INFERENCE_ENV_REL,
)

GENERATOR_VERSION = "t12-cluster-infrastructure/1.0.0"
SHARD_PLAN_SCHEMA_VERSION = "1.0.0"
SHARD_PLAN_VERSION = "1.0.0"
SHARD_ASSIGNMENT_METHOD = "ordinal_contiguous_balanced"


def repo_root(start: Path | None = None) -> Path:
    from ambiguity_manager.paths import repo_root as _repo_root

    return _repo_root(start)


def load_json_config(relpath: str, *, root: Path | None = None) -> dict[str, Any]:
    path = (root or repo_root()) / relpath
    return json.loads(path.read_text(encoding="utf-8"))


def config_sha256(relpath: str, *, root: Path | None = None) -> str:
    path = (root or repo_root()) / relpath
    return sha256_hex(path.read_bytes())


def load_preflight_configs(*, root: Path | None = None) -> dict[str, Any]:
    base = root or repo_root()
    immutable = load_immutable_selection(base)
    policy = load_json_config(CLUSTER_EXECUTION_POLICY_REL, root=base)
    environment = load_json_config(CLUSTER_INFERENCE_ENV_REL, root=base)
    return {
        "immutable_selection": immutable,
        "execution_policy": policy,
        "inference_environment": environment,
        "immutable_selection_hash": config_sha256(IMMUTABLE_SELECTION_REL, root=base),
        "execution_policy_hash": config_sha256(CLUSTER_EXECUTION_POLICY_REL, root=base),
        "inference_environment_hash": config_sha256(CLUSTER_INFERENCE_ENV_REL, root=base),
    }


def deterministic_json_dumps(payload: dict[str, Any]) -> str:
    return canonical_json_bytes(payload).decode("utf-8")
