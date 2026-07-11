"""Cluster manifest schema validation for T12 Stage B1–B3."""

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
CLUSTER_LIVE_VERIFICATION_REL = "configs/model/evidence/t12_cluster_live_verification.json"

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_HF_HUB_SNAPSHOT_PATTERN = re.compile(
    r"^\$\{T12_HF_CACHE\}/hub/models--Qwen--Qwen3-8B/snapshots/[0-9a-f]{40}$"
)
_VALID_EVIDENCE_STATUS = frozenset(
    {
        "template_pending_live_verification",
        "verified_offline",
        "verified_live_cluster",
        "verified_live_cluster_with_integrity_caveat",
        "pending_live_cluster_verification",
        "historical_measurement_only",
        "measurement_identifier_only",
        "size_and_sidecar_match",
        "deferred",
        "passed",
        "planned_unverified",
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
        "verified_live_cluster",
        "verified_live_cluster_with_integrity_caveat",
        "pending_live_cluster_verification",
        "historical_measurement_only",
        "measurement_identifier_only",
        "size_and_sidecar_match",
    }
)
_HISTORICAL_QWEN25 = "Qwen/Qwen2.5-1.5B-Instruct"
_INCORRECT_CACHE_ROOT_CAUSE = "INCORRECT_CACHE_DIR"
_OFFLINE_FLAGS = frozenset({"HF_HUB_OFFLINE=1", "TRANSFORMERS_OFFLINE=1"})


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
        has_timestamp = bool(field.get("measurement_timestamp"))
        has_date = bool(field.get("measurement_date"))
        if not has_timestamp and not has_date:
            errors.append(f"{path} measured values require measurement_timestamp or measurement_date")
        if has_date and field.get("measurement_time_precision") != "date_only":
            errors.append(f"{path}.measurement_time_precision must be date_only when using measurement_date")
        if not field.get("evidence_source"):
            errors.append(f"{path}.evidence_source required for measured values")


def _reject_historical_model_reference(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, str) and _HISTORICAL_QWEN25 in value:
        errors.append(f"{path} must not reference historical Qwen2.5 model")


def _validate_hf_cache_semantics(section: Any, path: str, errors: list[str]) -> None:
    if not isinstance(section, dict):
        errors.append(f"{path} must be an object")
        return
    if section.get("hf_home_template") != "${T12_HF_CACHE}":
        errors.append(f"{path}.hf_home_template must be ${{T12_HF_CACHE}}")
    if section.get("hf_hub_cache_derived_template") != "${T12_HF_CACHE}/hub":
        errors.append(f"{path}.hf_hub_cache_derived_template must be ${{T12_HF_CACHE}}/hub")
    if section.get("explicit_snapshot_download_cache_dir_must_be") != "${T12_HF_CACHE}/hub":
        errors.append(f"{path}.explicit_snapshot_download_cache_dir_must_be must be ${{T12_HF_CACHE}}/hub")
    if section.get("offline_resolution_root_cause") != _INCORRECT_CACHE_ROOT_CAUSE:
        errors.append(f"{path}.offline_resolution_root_cause must be INCORRECT_CACHE_DIR")
    if section.get("refs_directory_required") is True:
        errors.append(f"{path}.refs_directory_required must be false")
    flags = section.get("offline_flags_required")
    if not isinstance(flags, list) or set(flags) != _OFFLINE_FLAGS:
        errors.append(f"{path}.offline_flags_required must require HF_HUB_OFFLINE and TRANSFORMERS_OFFLINE")
    if section.get("network_fallback_permitted") is True or section.get("network_fallback_used") is True:
        errors.append(f"{path} must not permit network fallback")


def _validate_container_integrity(section: Any, path: str, errors: list[str]) -> None:
    if not isinstance(section, dict):
        errors.append(f"{path} must be an object")
        return
    expected = section.get("expected_immutable_sha256")
    sidecar = section.get("observed_sidecar_sha256")
    _require_sha256(expected, f"{path}.expected_immutable_sha256", errors)
    _require_sha256(sidecar, f"{path}.observed_sidecar_sha256", errors)
    if expected != _EXPECTED["container_sha256"]:
        errors.append(f"{path}.expected_immutable_sha256 must match immutable selection")
    if sidecar != expected:
        errors.append(f"{path}.observed_sidecar_sha256 must equal expected immutable sha256")
    if section.get("exact_size_bytes", section.get("size_bytes")) != _EXPECTED["container_size_bytes"]:
        errors.append(f"{path} container size must match immutable selection")
    if section.get("live_sha256_recomputed_during_b2") is True:
        errors.append(f"{path}.live_sha256_recomputed_during_b2 must be false")
    if section.get("live_sha256_status") != "deferred":
        errors.append(f"{path}.live_sha256_status must be deferred")
    if section.get("live_hash_verified") is True:
        errors.append(f"{path} must not claim live_hash_verified")


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
        if status not in {
            "planned_unverified",
            "verified_live_cluster_with_integrity_caveat",
        }:
            errors.append("inference environment_status invalid")
        container = data.get("container", {})
        sha_field = container.get("sha256", {})
        _require_sha256(sha_field.get("value"), "container.sha256.value", errors)
        size_field = container.get("size_bytes", {})
        if size_field.get("value") != _EXPECTED["container_size_bytes"]:
            errors.append("container.size_bytes.value must match immutable selection")
        integrity = container.get("integrity", {})
        _validate_container_integrity(integrity, "container.integrity", errors)
        hf_semantics = data.get("hf_cache_semantics")
        if hf_semantics:
            _validate_hf_cache_semantics(hf_semantics, "hf_cache_semantics", errors)
        snapshot_template = (
            data.get("model_identity", {}).get("snapshot_path_template", {}).get("value")
        )
        if snapshot_template and not _HF_HUB_SNAPSHOT_PATTERN.match(snapshot_template):
            errors.append("snapshot_path_template must use Hub cache layout")
        if data.get("adapter_load_verified") is True:
            errors.append("inference manifest must not claim adapter_load_verified")
        if data.get("model_weights_loaded_during_b2") is True:
            errors.append("inference manifest must not claim model weights loaded during B2")
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
    status = data.get("evidence_status")
    if status not in _VALID_EVIDENCE_STATUS:
        errors.append("evidence_status invalid")
    if data.get("measurement_time_precision") != "date_only":
        errors.append("measurement_time_precision must be date_only")

    smoke = data.get("historical_smoke_observation", {}).get(
        "explicit_node_used_during_smoke", data.get("scheduling_observation", {}).get(
            "explicit_node_used_during_smoke", {}
        )
    )
    if smoke.get("status") == "historical_measurement_only" and smoke.get("value") == "mscluster112":
        if "note" not in smoke:
            errors.append("historical node observation requires explanatory note")

    probe = data.get("gpu_tensor_probe", {})
    if probe.get("probe_node_is_permanent_requirement") is True:
        errors.append("gpu probe node must not be a permanent requirement")
    if probe.get("model_loaded") is True or probe.get("vllm_engine_started") is True:
        errors.append("gpu tensor probe must not claim model or vllm engine started")

    scheduling = data.get("scheduling_observation", {})
    if scheduling.get("qos_evidence_status") != "partial":
        errors.append("qos_evidence_status must be partial")
    if scheduling.get("permanent_job_limit_claim") is True:
        errors.append("must not claim permanent job limits from partial QoS evidence")
    node_states = scheduling.get("observed_node_states_at_measurement", {})
    if node_states and node_states.get("dynamic") is not True:
        errors.append("node states must be labelled dynamic")

    gpu_name = data.get("gpu", {}).get("name", {}).get("value", "")
    if "Blackwell" not in gpu_name:
        errors.append("gpu.name must record Blackwell class hardware")
    errors.extend(scan_forbidden_paths(data, path="cluster_hardware_evidence"))
    return errors


def validate_cluster_inference_evidence(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("environment_id") != "t12-cluster-inference":
        errors.append("environment_id must be t12-cluster-inference")
    if data.get("evidence_status") != "verified_live_cluster_with_integrity_caveat":
        errors.append("inference evidence must be verified_live_cluster_with_integrity_caveat")
    verified = data.get("verified_offline", {})
    _require_sha256(verified.get("container_sha256"), "verified_offline.container_sha256", errors)
    _require_positive_int(verified.get("container_size_bytes"), "verified_offline.container_size_bytes", errors)
    _validate_container_integrity(data.get("container_integrity", {}), "container_integrity", errors)
    _validate_hf_cache_semantics(data.get("hf_cache_semantics", {}), "hf_cache_semantics", errors)
    if data.get("must_not_reference_historical_model") != _HISTORICAL_QWEN25:
        errors.append("must_not_reference_historical_model must name Qwen2.5")
    live = data.get("verified_live_cluster", {})
    if live.get("vllm_engine_startup") is True:
        errors.append("vllm_engine_startup must remain false for B2/B2R evidence")
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
    if metadata.get("repository_files") != 15:
        errors.append("repository_metadata.repository_files must be 15")
    if metadata.get("total_size_bytes") != 16397461266:
        errors.append("repository_metadata.total_size_bytes must match observed inventory")
    if metadata.get("broken_symlinks") != 0:
        errors.append("repository_metadata.broken_symlinks must be 0")

    snapshot_template = data.get("snapshot_path_template")
    if not isinstance(snapshot_template, str) or not _HF_HUB_SNAPSHOT_PATTERN.match(snapshot_template):
        errors.append("snapshot_path_template must use Hub cache layout")

    offline = data.get("offline_resolution", {})
    if offline.get("status") != "passed":
        errors.append("offline_resolution.status must be passed")
    if offline.get("root_cause_classification") != _INCORRECT_CACHE_ROOT_CAUSE:
        errors.append("offline_resolution root cause must be INCORRECT_CACHE_DIR")
    if offline.get("refs_directory_causal") is True:
        errors.append("refs_directory must not be treated as causal")
    if offline.get("network_fallback_used") is True:
        errors.append("network_fallback_used must be false")

    verification = data.get("snapshot_verification", {})
    if verification.get("offline_metadata_verified") is not True:
        errors.append("offline_metadata_verified must be true")
    if verification.get("cluster_shared_cache_path_resolved") is not True:
        errors.append("cluster_shared_cache_path_resolved must be true after B2R")
    if verification.get("status") != "verified_offline":
        errors.append("snapshot_verification.status must be verified_offline")
    if data.get("historical_local_model_must_not_be_used") != _HISTORICAL_QWEN25:
        errors.append("historical_local_model_must_not_be_used must name Qwen2.5")
    errors.extend(scan_forbidden_paths(data, path="cluster_checkpoint_snapshot"))
    return errors


def validate_cluster_live_verification(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("ticket") != "T12":
        errors.append("ticket must be T12")
    if data.get("ingestion_stage") != "B3":
        errors.append("ingestion_stage must be B3")
    if data.get("measurement_time_precision") != "date_only":
        errors.append("measurement_time_precision must be date_only")

    governance = data.get("governance_state", {})
    if governance.get("t11_status") != "BLOCKED":
        errors.append("t11_status must remain BLOCKED")
    if governance.get("protected_data_used") is True or governance.get("research_pool_used") is True:
        errors.append("protected or research pool data must not be used")
    if governance.get("model_weights_loaded") is True:
        errors.append("model_weights_loaded must be false for B2/B2R evidence")
    if governance.get("selected_model_register_must_remain_null") is not True:
        errors.append("selected_model register must remain null")

    refs = data.get("cross_references", {})
    required_refs = (
        "immutable_selection",
        "execution_policy",
        "hardware_manifest",
        "inference_environment",
        "checkpoint_snapshot",
        "adr",
        "deviation_record",
    )
    for key in required_refs:
        if not refs.get(key):
            errors.append(f"cross_references.{key} is required")

    summary = data.get("status_summary", {})
    if summary.get("fresh_sif_live_hash") != "deferred":
        errors.append("fresh_sif_live_hash must be deferred")
    if summary.get("t11") != "BLOCKED":
        errors.append("status_summary.t11 must be BLOCKED")
    if summary.get("t12_complete") is True or summary.get("stage_c_complete") is True:
        errors.append("must not claim stage completion")

    _validate_container_integrity(data.get("container_summary", {}), "container_summary", errors)
    _validate_hf_cache_semantics(data.get("hf_cache_semantics", {}), "hf_cache_semantics", errors)

    gpu = data.get("gpu_probe_summary", {})
    if gpu.get("probe_node_is_permanent_requirement") is True:
        errors.append("gpu probe node must not be permanent requirement")
    if gpu.get("tensor_result") != [2.0, 4.0, 6.0]:
        errors.append("gpu tensor result must match observed probe")

    scheduler = data.get("scheduler_summary", {})
    if scheduler.get("qos_evidence_status") != "partial":
        errors.append("scheduler qos evidence must be partial")
    if scheduler.get("permanent_job_limit_claim") is True:
        errors.append("must not claim permanent job limits")

    if data.get("raw_terminal_transcripts_committed") is True:
        errors.append("raw terminal transcripts must not be committed")

    errors.extend(scan_forbidden_paths(data, path="cluster_live_verification"))
    return errors
