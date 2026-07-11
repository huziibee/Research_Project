"""Cluster manifest schema validation for T12 Stage B1."""

from __future__ import annotations

import re
from typing import Any

from ambiguity_manager.model.cluster.identities import _EXPECTED, validate_immutable_selection
from ambiguity_manager.model.cluster.path_policy import scan_forbidden_paths

CLUSTER_EXECUTION_POLICY_REL = "configs/model/cluster_execution_policy.json"
CLUSTER_INFERENCE_ENV_REL = "configs/environments/t12_cluster_inference.json"
CLUSTER_TRAINING_ENV_REL = "configs/environments/t12_cluster_training.json"
CLUSTER_HARDWARE_EVIDENCE_REL = "configs/model/evidence/t12_cluster_hardware_manifest.json"
CLUSTER_INFERENCE_EVIDENCE_REL = "configs/model/evidence/t12_cluster_inference_environment.json"
CLUSTER_CHECKPOINT_SNAPSHOT_REL = "configs/model/evidence/t12_cluster_checkpoint_snapshot.json"

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_VALID_EVIDENCE_STATUS = frozenset(
    {
        "template_pending_live_verification",
        "verified_offline",
        "pending_live_cluster_verification",
        "historical_measurement_only",
        "superseded_historical",
        "planned",
        "verified",
        "failed",
        "superseded",
    }
)
_VALID_VALUE_KIND = frozenset(
    {
        "measured",
        "immutable_expected",
        "pending_live_verification",
    }
)
_VALID_FIELD_STATUS = frozenset(
    {
        "verified_offline",
        "pending_live_cluster_verification",
        "historical_measurement_only",
    }
)
_HISTORICAL_QWEN25 = "Qwen/Qwen2.5-1.5B-Instruct"


def _require_sha256(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not _SHA256_PATTERN.match(value):
        errors.append(f"{path} must be a 64-character lowercase hex SHA-256")


def _require_positive_int(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        errors.append(f"{path} must be a non-negative integer")


def _validate_field_object(field: Any, path: str, errors: list[str]) -> None:
    if not isinstance(field, dict):
        errors.append(f"{path} must be an object")
        return
    value_kind = field.get("value_kind")
    if value_kind not in _VALID_VALUE_KIND:
        errors.append(f"{path}.value_kind invalid")
    status = field.get("status")
    if status not in _VALID_FIELD_STATUS and status not in _VALID_EVIDENCE_STATUS:
        errors.append(f"{path}.status invalid")
    if "value" not in field:
        errors.append(f"{path}.value is required")
    measured = value_kind == "measured"
    if measured:
        if not field.get("measurement_timestamp"):
            errors.append(f"{path}.measurement_timestamp required for measured values")
        if not field.get("evidence_source"):
            errors.append(f"{path}.evidence_source required for measured values")


def _reject_historical_model_reference(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, str) and _HISTORICAL_QWEN25 in value:
        errors.append(f"{path} must not reference historical Qwen2.5 model")


def validate_cluster_execution_policy(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != "1.0.0":
        errors.append("cluster_execution_policy.schema_version must be 1.0.0")
    if data.get("required_partition") != "biggpu":
        errors.append("required_partition must be biggpu")
    if data.get("require_exclusive_node") is not True:
        errors.append("require_exclusive_node must be true")
    if not isinstance(data.get("allowed_gpu_classes"), list) or not data["allowed_gpu_classes"]:
        errors.append("allowed_gpu_classes must be a non-empty list")
    allowlist = data.get("node_allowlist")
    denylist = data.get("node_denylist")
    if not isinstance(allowlist, list):
        errors.append("node_allowlist must be a list")
    if not isinstance(denylist, list):
        errors.append("node_denylist must be a list")
    if isinstance(allowlist, list) and len(allowlist) == 1 and allowlist[0] == "mscluster112":
        errors.append("node_allowlist must not permanently require one exact node")
    template = data.get("node_local_temp_template")
    if template != "/var/tmp/${USER}-apptainer-${SLURM_JOB_ID}":
        errors.append("node_local_temp_template must use approved /var/tmp template")
    errors.extend(scan_forbidden_paths(data, path="cluster_execution_policy"))
    return errors


def validate_cluster_environment_manifest(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("manifest_schema_version") != "1.0.0":
        errors.append("manifest_schema_version must be 1.0.0")
    if data.get("platform") != "wits_slurm_cluster":
        errors.append("platform must be wits_slurm_cluster")

    env_id = data.get("environment_id")
    role = data.get("role")
    status = data.get("environment_status")

    if env_id == "t12-cluster-inference":
        if role != "inference":
            errors.append("t12-cluster-inference role must be inference")
        container = data.get("container", {})
        sha_field = container.get("sha256", {})
        _require_sha256(sha_field.get("value"), "container.sha256.value", errors)
        size_field = container.get("size_bytes", {})
        if size_field.get("value") != _EXPECTED["container_size_bytes"]:
            errors.append("container.size_bytes.value must match immutable selection")
        if data.get("adapter_load_verified") is True:
            errors.append("inference manifest must not claim adapter_load_verified")
        model_repo = data.get("model_identity", {}).get("model_repository", {}).get("value")
        if model_repo != _EXPECTED["model_repository"]:
            errors.append("active inference manifest must reference Qwen3-8B")
        import json as _json

        _reject_historical_model_reference(_json.dumps(data), "manifest", errors)

    elif env_id == "t12-cluster-training":
        if role != "training":
            errors.append("t12-cluster-training role must be training")
        if status != "planned_unverified":
            errors.append("training environment_status must be planned_unverified")
        stack = data.get("training_stack", {})
        for flag in (
            "container_built",
            "peft_installed",
            "lora_attach_passed",
            "adapter_reload_passed",
        ):
            if stack.get(flag) is True:
                errors.append(f"training_stack.{flag} must not be true in Stage B1")
        if stack.get("optimiser_steps_performed", 0) != 0:
            errors.append("training_stack.optimiser_steps_performed must be 0")
        if stack.get("research_records_used", 0) != 0:
            errors.append("training_stack.research_records_used must be 0")
    else:
        errors.append("environment_id must be a known cluster environment")

    if status == "planned_unverified" and data.get("checkpoint_load_verified") is True:
        errors.append("planned_unverified cannot claim checkpoint_load_verified")

    errors.extend(scan_forbidden_paths(data, path="cluster_environment"))
    return errors


def validate_cluster_hardware_evidence(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("ticket") != "T12":
        errors.append("ticket must be T12")
    smoke = data.get("scheduling_observation", {}).get("explicit_node_used_during_smoke", {})
    if smoke.get("status") != "historical_measurement_only":
        errors.append("explicit_node_used_during_smoke must be historical_measurement_only")
    if smoke.get("value") == "mscluster112" and "note" not in smoke:
        errors.append("historical node observation requires explanatory note")
    gpu_name = data.get("gpu", {}).get("name", {}).get("value", "")
    if "Blackwell" not in gpu_name:
        errors.append("gpu.name must record Blackwell class hardware")
    errors.extend(scan_forbidden_paths(data, path="cluster_hardware_evidence"))
    return errors


def validate_cluster_inference_evidence(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("environment_id") != "t12-cluster-inference":
        errors.append("environment_id must be t12-cluster-inference")
    verified = data.get("verified_offline", {})
    _require_sha256(verified.get("container_sha256"), "verified_offline.container_sha256", errors)
    _require_positive_int(verified.get("container_size_bytes"), "verified_offline.container_size_bytes", errors)
    if data.get("must_not_reference_historical_model") != _HISTORICAL_QWEN25:
        errors.append("must_not_reference_historical_model must name Qwen2.5")
    errors.extend(scan_forbidden_paths(data, path="cluster_inference_evidence"))
    return errors


def validate_cluster_checkpoint_snapshot(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("model_repository", {}).get("value") != _EXPECTED["model_repository"]:
        errors.append("snapshot must reference Qwen3-8B")
    if data.get("model_revision", {}).get("value") != _EXPECTED["model_revision"]:
        errors.append("snapshot model_revision must match immutable selection")
    metadata = data.get("repository_metadata", {})
    _require_positive_int(metadata.get("total_size_bytes"), "repository_metadata.total_size_bytes", errors)
    if metadata.get("weight_shards") != 5:
        errors.append("repository_metadata.weight_shards must be 5")
    verification = data.get("snapshot_verification", {})
    if verification.get("offline_metadata_verified") is not True:
        errors.append("offline_metadata_verified must be true")
    if verification.get("cluster_weight_integrity_verified") is True:
        errors.append("cluster_weight_integrity_verified must remain false until live verification")
    if data.get("historical_local_model_must_not_be_used") != _HISTORICAL_QWEN25:
        errors.append("historical_local_model_must_not_be_used must name Qwen2.5")
    errors.extend(scan_forbidden_paths(data, path="cluster_checkpoint_snapshot"))
    return errors
