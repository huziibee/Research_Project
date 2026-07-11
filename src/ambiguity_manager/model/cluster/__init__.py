"""T12 cluster manifest and policy validation (CPU-only, stdlib)."""

from __future__ import annotations

from ambiguity_manager.model.cluster.identities import (
    IMMUTABLE_SELECTION_REL,
    load_immutable_selection,
)
from ambiguity_manager.model.cluster.manifest_schemas import (
    CLUSTER_CHECKPOINT_SNAPSHOT_REL,
    CLUSTER_EXECUTION_POLICY_REL,
    CLUSTER_HARDWARE_EVIDENCE_REL,
    CLUSTER_INFERENCE_ENV_REL,
    CLUSTER_INFERENCE_EVIDENCE_REL,
    CLUSTER_TRAINING_ENV_REL,
    validate_cluster_checkpoint_snapshot,
    validate_cluster_environment_manifest,
    validate_cluster_execution_policy,
    validate_cluster_hardware_evidence,
    validate_cluster_inference_evidence,
)
from ambiguity_manager.model.cluster.path_policy import (
    scan_forbidden_paths,
    validate_path_template,
)
from ambiguity_manager.model.cluster.preflight import run_preflight
from ambiguity_manager.model.cluster.snapshot_verify import verify_snapshot
from ambiguity_manager.model.cluster.sharding import plan_shards_from_jsonl
from ambiguity_manager.model.cluster.atomic_outputs import write_shard_outputs
from ambiguity_manager.model.cluster.run_state import evaluate_resume, merge_completed_shards

__all__ = [
    "IMMUTABLE_SELECTION_REL",
    "CLUSTER_EXECUTION_POLICY_REL",
    "CLUSTER_INFERENCE_ENV_REL",
    "CLUSTER_TRAINING_ENV_REL",
    "CLUSTER_HARDWARE_EVIDENCE_REL",
    "CLUSTER_INFERENCE_EVIDENCE_REL",
    "CLUSTER_CHECKPOINT_SNAPSHOT_REL",
    "load_immutable_selection",
    "validate_cluster_execution_policy",
    "validate_cluster_environment_manifest",
    "validate_cluster_hardware_evidence",
    "validate_cluster_inference_evidence",
    "validate_cluster_checkpoint_snapshot",
    "scan_forbidden_paths",
    "validate_path_template",
    "run_preflight",
    "verify_snapshot",
    "plan_shards_from_jsonl",
    "write_shard_outputs",
    "evaluate_resume",
    "merge_completed_shards",
]
