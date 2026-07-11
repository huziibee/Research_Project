"""Backend-neutral Slurm/cluster runtime preflight validation for T12."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ambiguity_manager.model.cluster._config_loader import load_preflight_configs
from ambiguity_manager.model.cluster.identities import ImmutableSelection
from ambiguity_manager.model.cluster.snapshot_verify import (
    SnapshotExpectations,
    verify_snapshot,
)

CONTAINER_INTEGRITY_METHODS = frozenset(
    {"full_sha256", "sidecar_sha256", "size_only", "not_checked"}
)

_COMPUTE_CAPABILITY_PATTERN = re.compile(r"^\d+\.\d+$")


@dataclass(frozen=True)
class PreflightResult:
    status: str
    timestamp: str
    allocated_hostname: str
    partition: str
    exclusive_allocation_confirmed: bool
    gpu_name: str
    vram_mib: int
    compute_capability: str
    driver_version: str
    cuda_available: bool
    container_path: str
    container_size_bytes: int
    container_sha_verification_method: str
    observed_container_sha256: str | None
    model_repository: str
    model_revision: str
    snapshot_path: str
    snapshot_inventory_result: dict[str, Any]
    offline_resolution_result: dict[str, Any]
    effective_hf_home: str
    effective_hub_cache: str
    rejection_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    immutable_selection_hash: str
    execution_policy_hash: str
    inference_environment_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "timestamp": self.timestamp,
            "allocated_hostname": self.allocated_hostname,
            "partition": self.partition,
            "exclusive_allocation_confirmed": self.exclusive_allocation_confirmed,
            "gpu_name": self.gpu_name,
            "vram_mib": self.vram_mib,
            "compute_capability": self.compute_capability,
            "driver_version": self.driver_version,
            "cuda_available": self.cuda_available,
            "container_path": self.container_path,
            "container_size_bytes": self.container_size_bytes,
            "container_sha_verification_method": self.container_sha_verification_method,
            "observed_container_sha256": self.observed_container_sha256,
            "model_repository": self.model_repository,
            "model_revision": self.model_revision,
            "snapshot_path": self.snapshot_path,
            "snapshot_inventory_result": self.snapshot_inventory_result,
            "offline_resolution_result": self.offline_resolution_result,
            "effective_hf_home": self.effective_hf_home,
            "effective_hub_cache": self.effective_hub_cache,
            "rejection_reasons": list(self.rejection_reasons),
            "warnings": list(self.warnings),
            "immutable_selection_hash": self.immutable_selection_hash,
            "execution_policy_hash": self.execution_policy_hash,
            "inference_environment_hash": self.inference_environment_hash,
        }


def _gpu_class_allowed(gpu_name: str, allowed_classes: list[dict[str, Any]]) -> bool:
    for gpu_class in allowed_classes:
        pattern = str(gpu_class.get("name_pattern", ""))
        if pattern and pattern in gpu_name:
            return True
    return False


def _gpu_class_requirements(
    gpu_name: str, allowed_classes: list[dict[str, Any]]
) -> tuple[int, str] | None:
    for gpu_class in allowed_classes:
        pattern = str(gpu_class.get("name_pattern", ""))
        if pattern and pattern in gpu_name:
            return int(gpu_class["minimum_vram_mib"]), str(gpu_class["minimum_compute_capability"])
    return None


def _compare_compute_capability(observed: str, minimum: str) -> bool:
    if not _COMPUTE_CAPABILITY_PATTERN.match(observed) or not _COMPUTE_CAPABILITY_PATTERN.match(minimum):
        return False
    obs_major, obs_minor = (int(part) for part in observed.split(".", 1))
    min_major, min_minor = (int(part) for part in minimum.split(".", 1))
    return (obs_major, obs_minor) >= (min_major, min_minor)


def _validate_runtime_facts_shape(facts: dict[str, Any]) -> list[str]:
    required = (
        "timestamp",
        "allocated_hostname",
        "partition",
        "exclusive_allocation_confirmed",
        "gpu_name",
        "vram_mib",
        "compute_capability",
        "driver_version",
        "cuda_available",
        "container_path",
        "container_size_bytes",
        "container_sha_verification_method",
        "model_repository",
        "model_revision",
        "snapshot_path",
        "offline_resolution_passed",
        "effective_hf_home",
        "effective_hub_cache",
        "network_fallback",
    )
    missing = [field for field in required if field not in facts]
    return [f"missing_runtime_fact:{field}" for field in missing]


def _validate_node_policy(
    hostname: str,
    allowlist: Any,
    denylist: Any,
) -> list[str]:
    rejections: list[str] = []
    denied = denylist if isinstance(denylist, list) else []
    allowed = allowlist if isinstance(allowlist, list) else []

    if hostname in denied:
        rejections.append("denied_node")
        return rejections

    if allowed and hostname not in allowed:
        rejections.append("node_allowlist_mismatch")

    return rejections


def run_preflight(
    runtime_facts: dict[str, Any],
    *,
    repo_root: Path | None = None,
    snapshot_expectations: SnapshotExpectations | None = None,
) -> PreflightResult:
    """Validate supplied runtime facts against pinned T12 cluster configs."""
    configs = load_preflight_configs(root=repo_root)
    immutable: ImmutableSelection = configs["immutable_selection"]
    policy: dict[str, Any] = configs["execution_policy"]
    environment: dict[str, Any] = configs["inference_environment"]

    rejections = _validate_runtime_facts_shape(runtime_facts)
    warnings: list[str] = []

    timestamp = str(runtime_facts.get("timestamp", ""))
    hostname = str(runtime_facts.get("allocated_hostname", ""))
    partition = str(runtime_facts.get("partition", ""))
    exclusive = bool(runtime_facts.get("exclusive_allocation_confirmed", False))
    gpu_name = str(runtime_facts.get("gpu_name", ""))
    vram_mib = int(runtime_facts.get("vram_mib", 0) or 0)
    compute_capability = str(runtime_facts.get("compute_capability", ""))
    driver_version = str(runtime_facts.get("driver_version", ""))
    cuda_available = bool(runtime_facts.get("cuda_available", False))
    container_path = str(runtime_facts.get("container_path", ""))
    container_size = int(runtime_facts.get("container_size_bytes", 0) or 0)
    integrity_method = str(runtime_facts.get("container_sha_verification_method", "not_checked"))
    observed_sha = runtime_facts.get("observed_container_sha256")
    observed_sha_str = str(observed_sha) if observed_sha is not None else None
    model_repository = str(runtime_facts.get("model_repository", ""))
    model_revision = str(runtime_facts.get("model_revision", ""))
    snapshot_path = str(runtime_facts.get("snapshot_path", ""))
    offline_passed = bool(runtime_facts.get("offline_resolution_passed", False))
    effective_hf_home = str(runtime_facts.get("effective_hf_home", ""))
    effective_hub_cache = str(runtime_facts.get("effective_hub_cache", ""))
    network_fallback = bool(runtime_facts.get("network_fallback", False))

    if rejections:
        return _build_result(
            status="fail",
            timestamp=timestamp,
            facts=runtime_facts,
            snapshot_inventory={},
            offline_result={"passed": offline_passed},
            rejections=tuple(rejections),
            warnings=tuple(warnings),
            configs=configs,
        )

    if partition != policy.get("required_partition"):
        rejections.append("partition_mismatch")
    if not exclusive:
        rejections.append("exclusive_allocation_not_confirmed")

    allowlist = policy.get("node_allowlist", [])
    denylist = policy.get("node_denylist", [])
    rejections.extend(_validate_node_policy(hostname, allowlist, denylist))

    if policy.get("reject_unapproved_gpu") and not _gpu_class_allowed(
        gpu_name, policy.get("allowed_gpu_classes", [])
    ):
        rejections.append("unapproved_gpu")
    else:
        requirements = _gpu_class_requirements(gpu_name, policy.get("allowed_gpu_classes", []))
        if requirements is None:
            rejections.append("unapproved_gpu")
        else:
            min_vram, min_compute = requirements
            if vram_mib < min_vram:
                rejections.append("insufficient_vram")
            if not _compare_compute_capability(compute_capability, min_compute):
                rejections.append("insufficient_compute_capability")

    if container_size != immutable.container_size_bytes:
        rejections.append("container_size_mismatch")

    if integrity_method not in CONTAINER_INTEGRITY_METHODS:
        rejections.append("invalid_container_integrity_method")
    elif integrity_method != "full_sha256":
        rejections.append("container_integrity_not_full_sha256")
    elif observed_sha_str != immutable.container_sha256:
        rejections.append("container_sha256_mismatch")

    if model_repository != immutable.model_repository:
        rejections.append("model_repository_mismatch")
    if model_revision != immutable.model_revision:
        rejections.append("model_revision_mismatch")

    hf_semantics = environment.get("hf_cache_semantics", {})
    expected_hf_home = hf_semantics.get("hf_home_template", "${T12_HF_CACHE}")
    expected_hub_cache = hf_semantics.get("hf_hub_cache_derived_template", "${T12_HF_CACHE}/hub")
    if effective_hf_home != expected_hf_home:
        rejections.append("incorrect_hf_home")
    if effective_hub_cache != expected_hub_cache:
        rejections.append("incorrect_hub_cache")
    if network_fallback:
        rejections.append("network_fallback_enabled")
    if not offline_passed:
        rejections.append("offline_resolution_failed")

    snapshot_inventory: dict[str, Any] = {}
    if snapshot_path:
        inventory = verify_snapshot(snapshot_path, expectations=snapshot_expectations)
        snapshot_inventory = inventory.to_dict()
        if inventory.status != "pass":
            rejections.extend(
                f"snapshot_inventory:{reason}" for reason in inventory.rejection_reasons
            )
    else:
        rejections.append("snapshot_path_missing")

    offline_result = {
        "passed": offline_passed,
        "network_fallback": network_fallback,
        "hf_home": effective_hf_home,
        "hub_cache": effective_hub_cache,
    }

    status = "pass" if not rejections else "fail"
    return _build_result(
        status=status,
        timestamp=timestamp,
        facts=runtime_facts,
        snapshot_inventory=snapshot_inventory,
        offline_result=offline_result,
        rejections=tuple(rejections),
        warnings=tuple(warnings),
        configs=configs,
    )


def _build_result(
    *,
    status: str,
    timestamp: str,
    facts: dict[str, Any],
    snapshot_inventory: dict[str, Any],
    offline_result: dict[str, Any],
    rejections: tuple[str, ...],
    warnings: tuple[str, ...],
    configs: dict[str, Any],
) -> PreflightResult:
    return PreflightResult(
        status=status,
        timestamp=timestamp,
        allocated_hostname=str(facts.get("allocated_hostname", "")),
        partition=str(facts.get("partition", "")),
        exclusive_allocation_confirmed=bool(facts.get("exclusive_allocation_confirmed", False)),
        gpu_name=str(facts.get("gpu_name", "")),
        vram_mib=int(facts.get("vram_mib", 0) or 0),
        compute_capability=str(facts.get("compute_capability", "")),
        driver_version=str(facts.get("driver_version", "")),
        cuda_available=bool(facts.get("cuda_available", False)),
        container_path=str(facts.get("container_path", "")),
        container_size_bytes=int(facts.get("container_size_bytes", 0) or 0),
        container_sha_verification_method=str(
            facts.get("container_sha_verification_method", "not_checked")
        ),
        observed_container_sha256=(
            str(facts["observed_container_sha256"])
            if facts.get("observed_container_sha256") is not None
            else None
        ),
        model_repository=str(facts.get("model_repository", "")),
        model_revision=str(facts.get("model_revision", "")),
        snapshot_path=str(facts.get("snapshot_path", "")),
        snapshot_inventory_result=snapshot_inventory,
        offline_resolution_result=offline_result,
        effective_hf_home=str(facts.get("effective_hf_home", "")),
        effective_hub_cache=str(facts.get("effective_hub_cache", "")),
        rejection_reasons=rejections,
        warnings=warnings,
        immutable_selection_hash=str(configs["immutable_selection_hash"]),
        execution_policy_hash=str(configs["execution_policy_hash"]),
        inference_environment_hash=str(configs["inference_environment_hash"]),
    )
