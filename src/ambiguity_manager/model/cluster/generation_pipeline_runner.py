"""Synthetic-only D-Final generation pipeline runner for T12 cluster smoke."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.cluster._config_loader import deterministic_json_dumps, repo_root
from ambiguity_manager.model.cluster.identities import load_immutable_selection
from ambiguity_manager.model.cluster.snapshot_verify import (
    CANONICAL_RESOLVED_BYTES,
    CANONICAL_RESOLVED_FILES,
)
from ambiguity_manager.model.generation_pipeline import (
    BackendIdentity,
    GenerationPipelineRequest,
    PipelineFinalStatus,
    PipelineIntegrityContext,
    SEMANTIC_CORRECTNESS_NOT_EVALUATED,
    StructuredDecodeReadiness,
    run_generation_pipeline,
    validate_integrity_context,
    validate_pipeline_request,
)
from ambiguity_manager.model.prediction_contract import (
    PredictionProvenancePolicy,
    model_semantic_output_schema_hash,
)
from ambiguity_manager.model.prompt_builder import PromptBuildRequest, build_prompt_messages
from ambiguity_manager.model.qwen3_renderer import Qwen3ChatTemplateRenderer, RunScopedVerifiedRenderer
from ambiguity_manager.model.repair_prompt import (
    PIPELINE_CONTRACT_HASH_METHOD,
    generation_pipeline_contract_hash,
    load_pipeline_contract,
)
from ambiguity_manager.model.response_mode_probe import (
    ProbeCandidateResult,
    ResponseModeProbePolicy,
    RunScopedResponseModeVerification,
    create_run_scoped_verification,
    evaluate_probe_candidate,
    load_response_mode_probe_policy,
    select_response_mode,
    verification_matches_run,
)
from ambiguity_manager.model.structured_decode import (
    StructuredDecodeMetadata,
    build_structured_sampling_params,
    load_structured_decode_contract,
    structured_decode_contract_hash,
)
from ambiguity_manager.model.vllm_pipeline_generator import VllmPipelineGenerator
from ambiguity_manager.schema.v2.records import LabelEligibility
from ambiguity_manager.schema.v2.taxonomies import AnnotationStatus, LabelConfidence, METRIC_ELIGIBILITY_FIELDS

DEFAULT_CONFIG_REL = Path("configs") / "cluster" / "t12_d_final_smoke.json"
COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
ARCHIVE_SHA_PATTERN = re.compile(r"^[0-9a-f]{64}$")
BackendFactory = Callable[..., Any]

AUTHORITATIVE_GENERATION = {
    "temperature": 0.0,
    "top_p": 1.0,
    "max_tokens": 2048,
}
AUTHORITATIVE_ENGINE = {
    "tensor_parallel_size": 1,
    "gpu_memory_utilization": 0.9,
}
AUTHORITATIVE_BATCH_SIZE = 1

EVIDENCE_FILES = (
    "response_mode_probe.json",
    "raw_attempts.jsonl",
    "attempt_ledgers.jsonl",
    "accepted_predictions.jsonl",
    "record_results.jsonl",
    "summary.json",
)


class DFinalRunnerError(Exception):
    """Raised when D-Final runner validation or execution fails."""


@dataclass(frozen=True)
class SourceIdentityManifest:
    schema_version: str
    source_commit_sha: str
    source_archive_sha256: str
    transfer_method: str
    archive_filename: str
    packaging_timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_commit_sha": self.source_commit_sha,
            "source_archive_sha256": self.source_archive_sha256,
            "transfer_method": self.transfer_method,
            "archive_filename": self.archive_filename,
            "packaging_timestamp": self.packaging_timestamp,
        }


@dataclass(frozen=True)
class DFinalSmokeConfig:
    schema_version: str
    config_version: str
    source_identity_mode: str
    model_repository: str
    model_revision: str
    container_sha256: str
    semantic_schema_hash: str
    structured_decode_contract_hash: str
    pipeline_contract_hash: str
    pipeline_contract_hash_method: str
    references: dict[str, str]
    tokenizer_snapshot: dict[str, Any]
    response_mode_candidate_order: tuple[str, ...]
    synthetic_inputs: dict[str, Any]
    batch_size: int
    generation: dict[str, Any]
    engine: dict[str, Any]
    offline_only: bool
    network_fallback_permitted: bool
    synthetic_only: bool
    persistent_engine_required: bool
    semantic_correctness_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "config_version": self.config_version,
            "source_identity_mode": self.source_identity_mode,
            "model_repository": self.model_repository,
            "model_revision": self.model_revision,
            "container_sha256": self.container_sha256,
            "semantic_schema_hash": self.semantic_schema_hash,
            "structured_decode_contract_hash": self.structured_decode_contract_hash,
            "pipeline_contract_hash": self.pipeline_contract_hash,
            "pipeline_contract_hash_method": self.pipeline_contract_hash_method,
            "references": dict(self.references),
            "tokenizer_snapshot": dict(self.tokenizer_snapshot),
            "response_mode_candidate_order": list(self.response_mode_candidate_order),
            "synthetic_inputs": dict(self.synthetic_inputs),
            "batch_size": self.batch_size,
            "generation": dict(self.generation),
            "engine": dict(self.engine),
            "offline_only": self.offline_only,
            "network_fallback_permitted": self.network_fallback_permitted,
            "synthetic_only": self.synthetic_only,
            "persistent_engine_required": self.persistent_engine_required,
            "semantic_correctness_status": self.semantic_correctness_status,
        }


@dataclass(frozen=True)
class DFinalRunResult:
    status: str
    run_id: str
    rejection_reasons: tuple[str, ...]
    run_dir: str
    engine_started: bool
    response_mode: str | None
    accepted_count: int
    rejected_after_attempts_count: int
    rejected_non_retryable_count: int
    semantic_correctness_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "run_id": self.run_id,
            "rejection_reasons": list(self.rejection_reasons),
            "run_dir": self.run_dir,
            "engine_started": self.engine_started,
            "response_mode": self.response_mode,
            "accepted_count": self.accepted_count,
            "rejected_after_attempts_count": self.rejected_after_attempts_count,
            "rejected_non_retryable_count": self.rejected_non_retryable_count,
            "semantic_correctness_status": self.semantic_correctness_status,
        }


def _generation_settings_for_compare(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "temperature": float(settings["temperature"]),
        "top_p": float(settings["top_p"]),
        "max_tokens": int(settings["max_tokens"]),
    }


def _engine_settings_for_compare(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "tensor_parallel_size": int(settings["tensor_parallel_size"]),
        "gpu_memory_utilization": float(settings["gpu_memory_utilization"]),
    }


def validate_source_identity_manifest(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != "1.0.0":
        errors.append("source_identity_manifest.schema_version must be 1.0.0")
    commit_sha = payload.get("source_commit_sha")
    if not isinstance(commit_sha, str) or not COMMIT_SHA_PATTERN.match(commit_sha):
        errors.append("source_commit_sha must be 40 lowercase hex characters")
    archive_sha = payload.get("source_archive_sha256")
    if not isinstance(archive_sha, str) or not ARCHIVE_SHA_PATTERN.match(archive_sha):
        errors.append("source_archive_sha256 must be 64 lowercase hex characters")
    if payload.get("transfer_method") != "git_archive":
        errors.append("transfer_method must be git_archive")
    if not payload.get("archive_filename"):
        errors.append("archive_filename is required")
    if not payload.get("packaging_timestamp"):
        errors.append("packaging_timestamp is required")
    return errors


def load_source_identity_manifest(path: Path | str) -> SourceIdentityManifest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = validate_source_identity_manifest(payload)
    if errors:
        raise DFinalRunnerError("; ".join(errors))
    return SourceIdentityManifest(
        schema_version=str(payload["schema_version"]),
        source_commit_sha=str(payload["source_commit_sha"]),
        source_archive_sha256=str(payload["source_archive_sha256"]),
        transfer_method=str(payload["transfer_method"]),
        archive_filename=str(payload["archive_filename"]),
        packaging_timestamp=str(payload["packaging_timestamp"]),
    )


def verify_source_identity(
    manifest: SourceIdentityManifest,
    archive_path: Path,
    *,
    extracted_root: Path | None = None,
) -> tuple[dict[str, Any], list[str]]:
    rejections: list[str] = []
    if not archive_path.is_file():
        rejections.append("source_archive_missing")
        return {}, rejections
    observed_archive_sha = sha256_hex(archive_path.read_bytes())
    if observed_archive_sha != manifest.source_archive_sha256:
        rejections.append("source_archive_hash_mismatch")
    source_identity = {
        "schema_version": manifest.schema_version,
        "source_commit_sha": manifest.source_commit_sha,
        "source_archive_sha256": manifest.source_archive_sha256,
        "transfer_method": manifest.transfer_method,
        "archive_filename": manifest.archive_filename,
        "packaging_timestamp": manifest.packaging_timestamp,
        "observed_archive_sha256": observed_archive_sha,
    }
    if extracted_root is not None:
        git_dir = extracted_root / ".git"
        if git_dir.is_dir():
            try:
                completed = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=extracted_root,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                head_sha = completed.stdout.strip()
                if head_sha != manifest.source_commit_sha:
                    rejections.append("source_commit_cross_check_mismatch")
                source_identity["git_cross_check_head_sha"] = head_sha
            except (OSError, subprocess.CalledProcessError) as exc:
                rejections.append(f"source_commit_cross_check_failed:{exc}")
    return source_identity, rejections


def validate_d_final_config(payload: dict[str, Any], *, root: Path) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != "1.0.0":
        errors.append("config.schema_version must be 1.0.0")
    if payload.get("source_commit_sha"):
        errors.append("config must not contain source_commit_sha")
    if payload.get("source_identity_mode") != "runtime_source_manifest_required":
        errors.append("config.source_identity_mode must be runtime_source_manifest_required")
    if payload.get("offline_only") is not True:
        errors.append("config.offline_only must be true")
    if payload.get("network_fallback_permitted") is not False:
        errors.append("config.network_fallback_permitted must be false")
    if payload.get("synthetic_only") is not True:
        errors.append("config.synthetic_only must be true")
    if payload.get("persistent_engine_required") is not True:
        errors.append("config.persistent_engine_required must be true")
    if payload.get("semantic_correctness_status") != SEMANTIC_CORRECTNESS_NOT_EVALUATED:
        errors.append("config.semantic_correctness_status must be not_evaluated")

    immutable = load_immutable_selection(root)
    if payload.get("model_repository") != immutable.model_repository:
        errors.append("config.model_repository mismatch")
    if payload.get("model_revision") != immutable.model_revision:
        errors.append("config.model_revision mismatch")
    if payload.get("container_sha256") != immutable.container_sha256:
        errors.append("config.container_sha256 mismatch")
    if payload.get("semantic_schema_hash") != model_semantic_output_schema_hash():
        errors.append("config.semantic_schema_hash mismatch")

    decode_contract = load_structured_decode_contract(root / payload["references"]["structured_decode_contract"])
    if payload.get("structured_decode_contract_hash") != structured_decode_contract_hash(decode_contract):
        errors.append("config.structured_decode_contract_hash mismatch")

    pipeline_path = root / payload["references"]["pipeline_contract"]
    if payload.get("pipeline_contract_hash_method") != PIPELINE_CONTRACT_HASH_METHOD:
        errors.append("config.pipeline_contract_hash_method mismatch")
    observed_pipeline_hash = generation_pipeline_contract_hash(pipeline_path)
    if payload.get("pipeline_contract_hash") != observed_pipeline_hash:
        errors.append("config.pipeline_contract_hash mismatch")

    if payload.get("response_mode_candidate_order") != ["default", "enable_thinking_false"]:
        errors.append("config.response_mode_candidate_order mismatch")

    if payload.get("batch_size") != AUTHORITATIVE_BATCH_SIZE:
        errors.append("config.batch_size mismatch")
    if _generation_settings_for_compare(payload.get("generation", {})) != AUTHORITATIVE_GENERATION:
        errors.append("config.generation mismatch")
    if _engine_settings_for_compare(payload.get("engine", {})) != AUTHORITATIVE_ENGINE:
        errors.append("config.engine mismatch")

    synthetic = payload.get("synthetic_inputs", {})
    if synthetic.get("required_record_count") != 4:
        errors.append("config.synthetic_inputs.required_record_count must be 4")
    return errors


def load_d_final_config(path: Path | str | None = None, *, root: Path | None = None) -> DFinalSmokeConfig:
    base = root or repo_root()
    target = Path(path) if path is not None else base / DEFAULT_CONFIG_REL
    payload = json.loads(target.read_text(encoding="utf-8"))
    errors = validate_d_final_config(payload, root=base)
    if errors:
        raise DFinalRunnerError("; ".join(errors))
    return DFinalSmokeConfig(
        schema_version=str(payload["schema_version"]),
        config_version=str(payload["config_version"]),
        source_identity_mode=str(payload["source_identity_mode"]),
        model_repository=str(payload["model_repository"]),
        model_revision=str(payload["model_revision"]),
        container_sha256=str(payload["container_sha256"]),
        semantic_schema_hash=str(payload["semantic_schema_hash"]),
        structured_decode_contract_hash=str(payload["structured_decode_contract_hash"]),
        pipeline_contract_hash=str(payload["pipeline_contract_hash"]),
        pipeline_contract_hash_method=str(payload["pipeline_contract_hash_method"]),
        references={key: str(value) for key, value in payload["references"].items()},
        tokenizer_snapshot=dict(payload["tokenizer_snapshot"]),
        response_mode_candidate_order=tuple(str(item) for item in payload["response_mode_candidate_order"]),
        synthetic_inputs=dict(payload["synthetic_inputs"]),
        batch_size=int(payload["batch_size"]),
        generation=dict(payload["generation"]),
        engine=dict(payload["engine"]),
        offline_only=bool(payload["offline_only"]),
        network_fallback_permitted=bool(payload["network_fallback_permitted"]),
        synthetic_only=bool(payload["synthetic_only"]),
        persistent_engine_required=bool(payload["persistent_engine_required"]),
        semantic_correctness_status=str(payload["semantic_correctness_status"]),
    )


def validate_runtime_config_consistency(
    *,
    config: DFinalSmokeConfig,
    probe_policy: ResponseModeProbePolicy,
    runtime_config: Any,
) -> list[str]:
    errors: list[str] = []
    d_gen = _generation_settings_for_compare(config.generation)
    p_gen = _generation_settings_for_compare(probe_policy.generation)
    runtime_generation = {
        key: value
        for key, value in runtime_config.generation.items()
        if key != "verification_status"
    }
    r_gen = _generation_settings_for_compare(runtime_generation)
    if d_gen != p_gen or d_gen != r_gen or d_gen != AUTHORITATIVE_GENERATION:
        errors.append("generation_settings_mismatch")

    d_engine = _engine_settings_for_compare(config.engine)
    runtime_engine = {
        key: value
        for key, value in runtime_config.engine.items()
        if key != "verification_status"
    }
    r_engine = _engine_settings_for_compare(runtime_engine)
    if d_engine != r_engine or d_engine != AUTHORITATIVE_ENGINE:
        errors.append("engine_settings_mismatch")

    if config.batch_size != runtime_config.batch_size or config.batch_size != AUTHORITATIVE_BATCH_SIZE:
        errors.append("batch_size_mismatch")

    if config.offline_only != runtime_config.offline_only:
        errors.append("offline_only_mismatch")
    if config.network_fallback_permitted != runtime_config.network_fallback_permitted:
        errors.append("network_fallback_mismatch")

    structured = runtime_config.structured_decode
    if structured is None or not structured.enabled:
        errors.append("structured_decode_not_enabled")
    elif structured.contract_relpath != config.references["structured_decode_contract"]:
        errors.append("structured_decode_contract_relpath_mismatch")
    elif structured.semantic_schema_relpath != "configs/model/schema/t12_model_semantic_output.schema.json":
        errors.append("structured_decode_schema_relpath_mismatch")

    if probe_policy.semantic_schema_hash != config.semantic_schema_hash:
        errors.append("probe_policy_semantic_schema_hash_mismatch")
    if probe_policy.structured_decode_contract_hash != config.structured_decode_contract_hash:
        errors.append("probe_policy_structured_decode_contract_hash_mismatch")
    return errors


def _load_synthetic_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        record = json.loads(stripped)
        if not isinstance(record, dict):
            raise DFinalRunnerError(f"malformed_record_type:{line_number}")
        if record.get("synthetic") is not True:
            raise DFinalRunnerError(f"non_synthetic_record:{line_number}")
        records.append(record)
    return records


def validate_synthetic_records(
    records: list[dict[str, Any]],
    *,
    config: DFinalSmokeConfig,
) -> list[str]:
    errors: list[str] = []
    expected_ids = list(config.synthetic_inputs["record_ids"])
    if len(records) != int(config.synthetic_inputs["required_record_count"]):
        errors.append(f"expected {config.synthetic_inputs['required_record_count']} records, got {len(records)}")
    observed_ids = [str(record.get("record_id", "")) for record in records]
    if observed_ids != expected_ids:
        errors.append(f"record_ids mismatch: expected {expected_ids}, got {observed_ids}")
    observed_hash = sha256_hex(canonical_json_bytes({"records": records}))
    if observed_hash != str(config.synthetic_inputs["input_hash"]):
        errors.append("synthetic input hash mismatch")

    required_fields = (
        "record_id",
        "ordinal",
        "synthetic",
        "command",
        "label_eligibility",
        "provenance_policy",
        "integrity_context",
        "expected_structural_disposition",
    )
    for record in records:
        for field in required_fields:
            if field not in record:
                errors.append(f"{record.get('record_id', '?')}: missing {field}")
        if record.get("synthetic") is not True:
            errors.append(f"{record.get('record_id', '?')}: non_synthetic")
    return errors


def validate_label_eligibility_strict(raw: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return ["label_eligibility must be an object"]
    unknown = sorted(set(raw) - set(METRIC_ELIGIBILITY_FIELDS))
    if unknown:
        errors.append(f"label_eligibility unknown fields: {unknown}")
    for field in METRIC_ELIGIBILITY_FIELDS:
        if field not in raw:
            errors.append(f"label_eligibility missing {field}")
        elif not isinstance(raw[field], bool):
            errors.append(f"label_eligibility.{field} must be boolean")
    if not errors:
        round_trip = LabelEligibility(**{name: bool(raw[name]) for name in METRIC_ELIGIBILITY_FIELDS}).to_dict()
        if round_trip != {name: bool(raw[name]) for name in METRIC_ELIGIBILITY_FIELDS}:
            errors.append("label_eligibility round_trip_mismatch")
    return errors


def validate_provenance_policy_strict(raw: Any) -> list[str]:
    errors: list[str] = []
    if raw is None:
        return ["provenance_policy is mandatory"]
    if not isinstance(raw, dict):
        return ["provenance_policy must be an object"]
    required = ("policy_version", "annotation_status", "label_confidence", "explanation")
    for field in required:
        if field not in raw:
            errors.append(f"provenance_policy missing {field}")
    if errors:
        return errors
    try:
        AnnotationStatus(str(raw["annotation_status"]))
    except ValueError:
        errors.append("provenance_policy.annotation_status invalid")
    try:
        LabelConfidence(str(raw["label_confidence"]))
    except ValueError:
        errors.append("provenance_policy.label_confidence invalid")
    if not errors:
        policy = PredictionProvenancePolicy(
            policy_version=str(raw["policy_version"]),
            annotation_status=AnnotationStatus(str(raw["annotation_status"])),
            label_confidence=LabelConfidence(str(raw["label_confidence"])),
            explanation=str(raw["explanation"]),
            evidence_identifier=str(raw["evidence_identifier"]) if raw.get("evidence_identifier") is not None else None,
        )
        round_trip = {
            "policy_version": policy.policy_version,
            "annotation_status": policy.annotation_status.value,
            "label_confidence": policy.label_confidence.value,
            "explanation": policy.explanation,
        }
        if policy.evidence_identifier is not None:
            round_trip["evidence_identifier"] = policy.evidence_identifier
        for key, value in round_trip.items():
            if raw.get(key) != value:
                errors.append(f"provenance_policy round_trip mismatch for {key}")
    return errors


def _label_eligibility(raw: dict[str, Any]) -> LabelEligibility:
    return LabelEligibility(**{name: bool(raw[name]) for name in METRIC_ELIGIBILITY_FIELDS})


def _provenance_policy(raw: dict[str, Any]) -> PredictionProvenancePolicy:
    return PredictionProvenancePolicy(
        policy_version=str(raw["policy_version"]),
        annotation_status=AnnotationStatus(str(raw["annotation_status"])),
        label_confidence=LabelConfidence(str(raw["label_confidence"])),
        explanation=str(raw["explanation"]),
        evidence_identifier=str(raw["evidence_identifier"]) if raw.get("evidence_identifier") is not None else None,
    )


def _pipeline_request_from_record(
    record: dict[str, Any],
    *,
    container_sha: str,
) -> GenerationPipelineRequest:
    return GenerationPipelineRequest(
        caller_request_id=f"pred:{record['record_id']}",
        synthetic=True,
        command=str(record["command"]),
        label_eligibility=_label_eligibility(record["label_eligibility"]),
        provenance_policy=_provenance_policy(record["provenance_policy"]),
        source_dataset=str(record.get("source_dataset", "t12_d_final_synthetic")),
        integrity_context=PipelineIntegrityContext.from_mapping(record["integrity_context"]),
        scene_context=record.get("scene_context"),
        dialogue_history=list(record.get("dialogue_history") or []),
        capability_context=record.get("capability_context"),
        container_sha=container_sha,
    )


def validate_pipeline_requests_from_records(
    records: list[dict[str, Any]],
    *,
    container_sha: str,
) -> tuple[list[GenerationPipelineRequest], list[str]]:
    errors: list[str] = []
    requests: list[GenerationPipelineRequest] = []
    for record in records:
        record_id = str(record.get("record_id", "?"))
        errors.extend(
            f"{record_id}:{item}" for item in validate_label_eligibility_strict(record.get("label_eligibility"))
        )
        errors.extend(
            f"{record_id}:{item}" for item in validate_provenance_policy_strict(record.get("provenance_policy"))
        )
        errors.extend(
            f"{record_id}:{item}" for item in validate_integrity_context(record.get("integrity_context"))
        )
        if errors:
            continue
        request = _pipeline_request_from_record(record, container_sha=container_sha)
        errors.extend(f"{record_id}:{item}" for item in validate_pipeline_request(request))
        requests.append(request)
    if errors:
        return [], errors
    return requests, []


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = deterministic_json_dumps(payload)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _atomic_write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [deterministic_json_dumps(row) for row in rows]
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line)
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


_OBSOLETE_FLAT_PREFLIGHT_KEYS = (
    "offline_resolution_passed",
    "network_fallback",
    "snapshot_inventory_status",
)


def _validate_preflight(preflight: dict[str, Any], *, config: DFinalSmokeConfig) -> list[str]:
    rejections: list[str] = []
    if not isinstance(preflight, dict):
        rejections.append("preflight_not_object")
        return rejections

    if any(key in preflight for key in _OBSOLETE_FLAT_PREFLIGHT_KEYS):
        rejections.append("preflight_obsolete_flat_shape")

    if preflight.get("status") != "pass":
        rejections.append("preflight_not_pass")
    if preflight.get("model_repository") != config.model_repository:
        rejections.append("preflight_model_repository_mismatch")
    if preflight.get("model_revision") != config.model_revision:
        rejections.append("preflight_model_revision_mismatch")
    observed_sha = preflight.get("observed_container_sha256")
    if observed_sha != config.container_sha256:
        rejections.append("container_sha_mismatch")

    offline = preflight.get("offline_resolution_result")
    if "offline_resolution_result" not in preflight:
        rejections.append("preflight_offline_resolution_result_missing")
    elif offline is None:
        rejections.append("preflight_offline_resolution_result_null")
    elif not isinstance(offline, dict):
        rejections.append("preflight_offline_resolution_result_not_object")
    else:
        if "passed" not in offline:
            rejections.append("preflight_offline_resolution_passed_missing")
        elif offline.get("passed") is not True:
            rejections.append("preflight_offline_resolution_not_passed")
        if "network_fallback" not in offline:
            rejections.append("preflight_network_fallback_missing")
        elif offline.get("network_fallback") is not False:
            rejections.append("preflight_network_fallback_not_false")

    snapshot = preflight.get("snapshot_inventory_result")
    if "snapshot_inventory_result" not in preflight:
        rejections.append("preflight_snapshot_inventory_result_missing")
    elif snapshot is None:
        rejections.append("preflight_snapshot_inventory_result_null")
    elif not isinstance(snapshot, dict):
        rejections.append("preflight_snapshot_inventory_result_not_object")
    else:
        if snapshot.get("status") != "pass":
            rejections.append("preflight_snapshot_inventory_not_pass")
        repository = snapshot.get("repository")
        if repository is not None and repository != config.model_repository:
            rejections.append("preflight_snapshot_repository_mismatch")
        revision_directory = snapshot.get("revision_directory")
        if revision_directory is not None and revision_directory != config.model_revision:
            rejections.append("preflight_snapshot_revision_mismatch")
        resolved_file_count = snapshot.get("resolved_file_count")
        if resolved_file_count is not None and resolved_file_count != CANONICAL_RESOLVED_FILES:
            rejections.append("preflight_snapshot_resolved_file_count_mismatch")
        resolved_total_bytes = snapshot.get("resolved_total_bytes")
        if resolved_total_bytes is not None and resolved_total_bytes != CANONICAL_RESOLVED_BYTES:
            rejections.append("preflight_snapshot_resolved_total_bytes_mismatch")

    return rejections


def _file_evidence_entry(path: Path, *, relative_name: str) -> dict[str, Any]:
    data = path.read_bytes()
    entry: dict[str, Any] = {
        "filename": relative_name,
        "sha256": sha256_hex(data),
        "byte_size": len(data),
    }
    if path.suffix == ".jsonl":
        entry["row_count"] = sum(1 for line in data.decode("utf-8").splitlines() if line.strip())
    return entry


def _finalize_manifest(
    run_dir: Path,
    *,
    manifest_base: dict[str, Any],
) -> dict[str, Any]:
    output_hashes: dict[str, Any] = {}
    for filename in EVIDENCE_FILES:
        path = run_dir / filename
        if path.is_file():
            output_hashes[filename] = _file_evidence_entry(path, relative_name=filename)
    verification_path = run_dir / "response_mode_verification.json"
    if verification_path.is_file():
        output_hashes["response_mode_verification.json"] = _file_evidence_entry(
            verification_path,
            relative_name="response_mode_verification.json",
        )
    manifest = dict(manifest_base)
    manifest["output_file_hashes"] = output_hashes
    return manifest


def _write_evidence_package(
    run_dir: Path,
    *,
    status: str,
    run_id: str,
    rejection_reasons: tuple[str, ...],
    measurement_timestamp: str,
    manifest_base: dict[str, Any],
    config: DFinalSmokeConfig | None = None,
    probe_results: list[ProbeCandidateResult] | None = None,
    verification: RunScopedResponseModeVerification | None = None,
    raw_attempt_rows: list[dict[str, Any]] | None = None,
    ledger_rows: list[dict[str, Any]] | None = None,
    accepted_rows: list[dict[str, Any]] | None = None,
    record_result_rows: list[dict[str, Any]] | None = None,
    selected_mode: str | None = None,
    accepted_count: int = 0,
    rejected_after_attempts_count: int = 0,
    rejected_non_retryable_count: int = 0,
) -> None:
    _ = config
    probe_payload = {
        "candidates": [item.to_dict() for item in (probe_results or [])],
        "selected_mode": selected_mode,
    }
    _atomic_write_json(run_dir / "response_mode_probe.json", probe_payload)
    if verification is not None:
        _atomic_write_json(run_dir / "response_mode_verification.json", verification.to_dict())
    _atomic_write_jsonl(run_dir / "raw_attempts.jsonl", raw_attempt_rows or [])
    _atomic_write_jsonl(run_dir / "attempt_ledgers.jsonl", ledger_rows or [])
    _atomic_write_jsonl(run_dir / "accepted_predictions.jsonl", accepted_rows or [])
    _atomic_write_jsonl(run_dir / "record_results.jsonl", record_result_rows or [])
    summary = {
        "status": status,
        "run_id": run_id,
        "accepted_count": accepted_count,
        "rejected_after_attempts_count": rejected_after_attempts_count,
        "rejected_non_retryable_count": rejected_non_retryable_count,
        "semantic_correctness_status": SEMANTIC_CORRECTNESS_NOT_EVALUATED,
        "response_mode": selected_mode,
        "rejection_reasons": list(rejection_reasons),
        "measurement_timestamp": measurement_timestamp,
        "generation_call_count": int(manifest_base.get("generation_call_count", 0)),
    }
    _atomic_write_json(run_dir / "summary.json", summary)
    manifest = _finalize_manifest(run_dir, manifest_base=manifest_base)
    _atomic_write_json(run_dir / "run_manifest.json", manifest)


def _probe_structured_decode_metadata(
    backend: Any,
    *,
    structured_readiness: StructuredDecodeReadiness | None,
) -> dict[str, Any] | None:
    metadata = getattr(backend, "last_structured_decode_metadata", None)
    if metadata:
        return dict(metadata)
    if structured_readiness is not None:
        return structured_readiness.metadata.to_dict()
    return None


def _unconstrained_fallback_indicated(
    metadata: dict[str, Any] | None,
    *,
    structured_readiness: StructuredDecodeReadiness | None,
) -> bool:
    if structured_readiness is not None and structured_readiness.unconstrained_fallback_indicated:
        return True
    if metadata is None:
        return False
    return bool(metadata.get("unconstrained_fallback_indicated"))


def run_d_final_smoke(
    *,
    run_dir: Path,
    preflight_result: dict[str, Any],
    config: DFinalSmokeConfig | None = None,
    config_path: Path | None = None,
    root: Path | None = None,
    source_identity_manifest: SourceIdentityManifest | None = None,
    source_identity_manifest_path: Path | None = None,
    source_archive: Path | None = None,
    extracted_source_root: Path | None = None,
    slurm_log_path: str | None = None,
    backend_factory: BackendFactory | None = None,
    tokenizer_factory: Callable[..., Any] | None = None,
    probe_generator: Callable[..., str] | None = None,
    record_generator: Callable[..., str] | None = None,
    structured_decode_readiness_override: StructuredDecodeReadiness | None = None,
    measurement_timestamp: str,
    snapshot_path: Path | str | None = None,
) -> DFinalRunResult:
    base = (root or repo_root()).resolve()
    run_id = run_dir.name

    if run_dir.exists():
        return DFinalRunResult(
            status="BLOCKED",
            run_id=run_id,
            rejection_reasons=("run_directory_exists",),
            run_dir=str(run_dir),
            engine_started=False,
            response_mode=None,
            accepted_count=0,
            rejected_after_attempts_count=0,
            rejected_non_retryable_count=0,
            semantic_correctness_status=SEMANTIC_CORRECTNESS_NOT_EVALUATED,
        )

    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return DFinalRunResult(
            status="BLOCKED",
            run_id=run_id,
            rejection_reasons=("run_directory_exists",),
            run_dir=str(run_dir),
            engine_started=False,
            response_mode=None,
            accepted_count=0,
            rejected_after_attempts_count=0,
            rejected_non_retryable_count=0,
            semantic_correctness_status=SEMANTIC_CORRECTNESS_NOT_EVALUATED,
        )

    preflight_hash = sha256_hex(canonical_json_bytes(preflight_result))
    manifest_base: dict[str, Any] = {
        "run_id": run_id,
        "preflight_hash": preflight_hash,
        "engine_start_count": 0,
        "generation_call_count": 0,
        "semantic_correctness_status": SEMANTIC_CORRECTNESS_NOT_EVALUATED,
        "slurm_log_path": slurm_log_path,
    }

    try:
        active_config = config or load_d_final_config(config_path, root=base)
    except DFinalRunnerError as exc:
        rejection_reasons = tuple(str(exc).split("; "))
        pipeline_path = base / "configs/model/t12_generation_pipeline_contract.json"
        if pipeline_path.is_file():
            manifest_base["pipeline_contract_file_sha256"] = sha256_hex(pipeline_path.read_bytes())
        _write_evidence_package(
            run_dir,
            status="BLOCKED",
            run_id=run_id,
            rejection_reasons=rejection_reasons,
            measurement_timestamp=measurement_timestamp,
            manifest_base={
                **manifest_base,
                "status": "BLOCKED",
                "rejection_reasons": list(rejection_reasons),
            },
        )
        return DFinalRunResult(
            status="BLOCKED",
            run_id=run_id,
            rejection_reasons=rejection_reasons,
            run_dir=str(run_dir),
            engine_started=False,
            response_mode=None,
            accepted_count=0,
            rejected_after_attempts_count=0,
            rejected_non_retryable_count=0,
            semantic_correctness_status=SEMANTIC_CORRECTNESS_NOT_EVALUATED,
        )

    pipeline_path = base / active_config.references["pipeline_contract"]
    manifest_base.update(
        {
            "config_hash": sha256_hex(canonical_json_bytes(active_config.to_dict())),
            "model_repository": active_config.model_repository,
            "model_revision": active_config.model_revision,
            "container_sha256": active_config.container_sha256,
            "semantic_schema_hash": active_config.semantic_schema_hash,
            "structured_decode_contract_hash": active_config.structured_decode_contract_hash,
            "pipeline_contract_hash": active_config.pipeline_contract_hash,
            "pipeline_contract_hash_method": active_config.pipeline_contract_hash_method,
            "pipeline_contract_file_sha256": sha256_hex(pipeline_path.read_bytes()),
            "input_hash": active_config.synthetic_inputs["input_hash"],
        }
    )

    rejections = _validate_preflight(preflight_result, config=active_config)

    # Preload immutable selection under the authoritative source root so probe and
    # record validation never depend on process CWD.
    immutable = None
    try:
        immutable = load_immutable_selection(base)
    except Exception as exc:  # noqa: BLE001
        rejections.append(f"immutable_selection_load_failed:{exc}")
    if immutable is not None:
        if immutable.model_repository != active_config.model_repository:
            rejections.append("immutable_selection_model_repository_mismatch")
        if immutable.model_revision != active_config.model_revision:
            rejections.append("immutable_selection_model_revision_mismatch")

    manifest: SourceIdentityManifest | None = source_identity_manifest
    if manifest is None and source_identity_manifest_path is not None:
        try:
            manifest = load_source_identity_manifest(source_identity_manifest_path)
        except DFinalRunnerError as exc:
            rejections.append(str(exc))
    if manifest is None:
        rejections.append("source_identity_manifest_missing")
    elif source_archive is None:
        rejections.append("source_archive_missing")
    else:
        source_identity, source_rejections = verify_source_identity(
            manifest,
            source_archive,
            extracted_root=extracted_source_root or base,
        )
        manifest_base["source_identity"] = source_identity
        rejections.extend(source_rejections)

    input_path = base / str(active_config.synthetic_inputs["relpath"])
    records: list[dict[str, Any]] = []
    try:
        records = _load_synthetic_records(input_path)
    except DFinalRunnerError as exc:
        rejections.append(str(exc))
    if records:
        rejections.extend(validate_synthetic_records(records, config=active_config))

    pipeline_requests: list[GenerationPipelineRequest] = []
    if records and not rejections:
        pipeline_requests, request_errors = validate_pipeline_requests_from_records(
            records,
            container_sha=active_config.container_sha256,
        )
        rejections.extend(request_errors)

    probe_policy: ResponseModeProbePolicy | None = None
    runtime_config: Any | None = None
    decode_contract = None
    schema_hash = model_semantic_output_schema_hash()
    contract_hash = active_config.structured_decode_contract_hash

    if not rejections:
        probe_policy = load_response_mode_probe_policy(base / active_config.references["response_mode_probe_policy"])
        manifest_base["response_mode_policy_hash"] = sha256_hex(
            canonical_json_bytes(probe_policy.to_dict())
        )
        from ambiguity_manager.model.backends.vllm_batch import create_vllm_batch_backend, load_runtime_config

        runtime_config_path = base / active_config.references["runtime_config"]
        runtime_config = load_runtime_config(runtime_config_path, repo_root=base)
        manifest_base["runtime_config_hash"] = runtime_config.config_hash
        rejections.extend(
            validate_runtime_config_consistency(
                config=active_config,
                probe_policy=probe_policy,
                runtime_config=runtime_config,
            )
        )
        decode_contract = load_structured_decode_contract(base / active_config.references["structured_decode_contract"])
        contract_hash = structured_decode_contract_hash(decode_contract)
        pipeline_contract = load_pipeline_contract(base / active_config.references["pipeline_contract"])
        from ambiguity_manager.model.generation_policy import DEFAULT_POLICY_REL, load_generation_policy

        generation_policy = load_generation_policy(base / DEFAULT_POLICY_REL)

    if rejections:
        _write_evidence_package(
            run_dir,
            status="BLOCKED",
            run_id=run_id,
            rejection_reasons=tuple(rejections),
            measurement_timestamp=measurement_timestamp,
            config=active_config,
            manifest_base={**manifest_base, "status": "BLOCKED", "rejection_reasons": list(rejections)},
        )
        return DFinalRunResult(
            status="BLOCKED",
            run_id=run_id,
            rejection_reasons=tuple(rejections),
            run_dir=str(run_dir),
            engine_started=False,
            response_mode=None,
            accepted_count=0,
            rejected_after_attempts_count=0,
            rejected_non_retryable_count=0,
            semantic_correctness_status=SEMANTIC_CORRECTNESS_NOT_EVALUATED,
        )

    assert probe_policy is not None
    assert runtime_config is not None
    assert decode_contract is not None

    snapshot = Path(snapshot_path) if snapshot_path is not None else Path("/offline/tokenizer/snapshot")
    renderer = Qwen3ChatTemplateRenderer(
        snapshot_path=snapshot,
        model_repository=active_config.model_repository,
        immutable_revision=active_config.model_revision,
        expected_tokenizer_hashes={
            str(key): str(value)
            for key, value in active_config.tokenizer_snapshot["artefact_hashes"].items()
        },
        expected_immutable_identity=(
            (immutable.model_repository, immutable.model_revision) if immutable is not None else None
        ),
        tokenizer_factory=tokenizer_factory,
    )

    probe_messages = build_prompt_messages(
        PromptBuildRequest(command=probe_policy.synthetic_probe_command)
    )
    probe_candidates = [
        renderer.render_candidate(probe_messages, mode=mode)
        for mode in active_config.response_mode_candidate_order
    ]

    backend = (
        backend_factory(runtime_config, repo_root=base)
        if backend_factory is not None
        else create_vllm_batch_backend(runtime_config, repo_root=base)
    )

    structured_readiness: StructuredDecodeReadiness | None = structured_decode_readiness_override
    if structured_readiness is None:
        try:
            build_result = build_structured_sampling_params(
                {key: value for key, value in runtime_config.generation.items() if key != "verification_status"},
                decode_contract,
                repo_root=base,
            )
            structured_readiness = StructuredDecodeReadiness(metadata=build_result.metadata)
            manifest_base["structured_decode_metadata"] = build_result.metadata.to_dict()
        except Exception as exc:  # noqa: BLE001
            rejections = (f"structured_decode_construction_failed:{exc}",)
            _write_evidence_package(
                run_dir,
                status="BLOCKED",
                run_id=run_id,
                rejection_reasons=rejections,
                measurement_timestamp=measurement_timestamp,
                config=active_config,
                manifest_base={**manifest_base, "status": "BLOCKED", "rejection_reasons": list(rejections)},
            )
            return DFinalRunResult(
                status="BLOCKED",
                run_id=run_id,
                rejection_reasons=rejections,
                run_dir=str(run_dir),
                engine_started=False,
                response_mode=None,
                accepted_count=0,
                rejected_after_attempts_count=0,
                rejected_non_retryable_count=0,
                semantic_correctness_status=SEMANTIC_CORRECTNESS_NOT_EVALUATED,
            )

    engine_started = False
    try:
        backend.start()
        engine_started = True
        manifest_base["engine_start_count"] = 1
    except Exception as exc:  # noqa: BLE001
        rejections = (f"engine_startup_failed:{exc}",)
        _write_evidence_package(
            run_dir,
            status="BLOCKED",
            run_id=run_id,
            rejection_reasons=rejections,
            measurement_timestamp=measurement_timestamp,
            config=active_config,
            manifest_base={**manifest_base, "status": "BLOCKED", "rejection_reasons": list(rejections)},
        )
        return DFinalRunResult(
            status="BLOCKED",
            run_id=run_id,
            rejection_reasons=rejections,
            run_dir=str(run_dir),
            engine_started=False,
            response_mode=None,
            accepted_count=0,
            rejected_after_attempts_count=0,
            rejected_non_retryable_count=0,
            semantic_correctness_status=SEMANTIC_CORRECTNESS_NOT_EVALUATED,
        )

    generator = VllmPipelineGenerator(backend=backend)
    probe_results: list[ProbeCandidateResult] = []

    try:
        for index, candidate in enumerate(probe_candidates):
            if probe_generator is not None:
                raw_output = probe_generator(
                    rendered_prompt=candidate.rendered_prompt_text,
                    candidate_mode=candidate.candidate_mode,
                )
                generation_status = "success"
                finish_reason = "stop"
                engine_request_id = f"probe-{index}"
                manifest_base["generation_call_count"] = int(manifest_base.get("generation_call_count", 0)) + 1
            else:
                output = generator.generate(
                    rendered_prompt=candidate.rendered_prompt_text,
                    attempt_index=index,
                    caller_request_id=f"probe:{candidate.candidate_mode}",
                )
                raw_output = output.raw_output
                generation_status = output.generation_status
                finish_reason = output.finish_reason
                engine_request_id = output.engine_request_id
                manifest_base["generation_call_count"] = int(manifest_base.get("generation_call_count", 0)) + 1
                prompt_tokens = output.prompt_tokens
                completion_tokens = output.completion_tokens
            if probe_generator is not None:
                prompt_tokens = None
                completion_tokens = None

            metadata = _probe_structured_decode_metadata(
                backend,
                structured_readiness=structured_readiness,
            )
            fallback = _unconstrained_fallback_indicated(
                metadata,
                structured_readiness=structured_readiness,
            )
            try:
                probe_results.append(
                    evaluate_probe_candidate(
                        candidate_mode=candidate.candidate_mode,
                        rendered_prompt_hash=candidate.rendered_prompt_hash,
                        raw_output=raw_output,
                        generation_status=generation_status,
                        finish_reason=finish_reason,
                        engine_request_id=engine_request_id,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        model_repository=active_config.model_repository,
                        model_revision=active_config.model_revision,
                        schema_hash=schema_hash,
                        contract_hash=contract_hash,
                        policy=probe_policy,
                        contract=decode_contract,
                        immutable=immutable,
                        structured_decode_metadata=metadata,
                        unconstrained_fallback_indicated=fallback,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                # Preserve raw probe output in evidence even if evaluation crashes.
                probe_results.append(
                    ProbeCandidateResult(
                        candidate_mode=candidate.candidate_mode,
                        rendered_prompt_hash=candidate.rendered_prompt_hash,
                        raw_output=raw_output,
                        raw_output_hash=sha256_hex(raw_output.encode("utf-8")) if raw_output else "",
                        generation_status=generation_status,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        direct_json_parse_status="skipped",
                        raw_object_status="skipped",
                        local_repair_attempts=0,
                        local_repair_log=(),
                        semantic_schema_status="skipped",
                        semantic_schema_error=None,
                        thinking_markers_present=False,
                        prose_before_json=False,
                        prose_after_json=False,
                        engine_request_id=engine_request_id,
                        finish_reason=finish_reason,
                        unconstrained_fallback_indicated=fallback,
                        structured_decode_metadata=metadata,
                        model_repository=active_config.model_repository,
                        model_revision=active_config.model_revision,
                        schema_hash=schema_hash,
                        contract_hash=contract_hash,
                        passed=False,
                        failure_reasons=(f"unexpected_probe_evaluator_exception:{type(exc).__name__}",),
                    )
                )
                raise

        selected = select_response_mode(probe_results, policy=probe_policy)
        if selected is None:
            rejections = ("no_passing_response_mode",)
            _write_evidence_package(
                run_dir,
                status="BLOCKED",
                run_id=run_id,
                rejection_reasons=rejections,
                measurement_timestamp=measurement_timestamp,
                config=active_config,
                probe_results=probe_results,
                manifest_base={
                    **manifest_base,
                    "status": "BLOCKED",
                    "rejection_reasons": list(rejections),
                    "response_mode": None,
                },
            )
            return DFinalRunResult(
                status="BLOCKED",
                run_id=run_id,
                rejection_reasons=rejections,
                run_dir=str(run_dir),
                engine_started=engine_started,
                response_mode=None,
                accepted_count=0,
                rejected_after_attempts_count=0,
                rejected_non_retryable_count=0,
                semantic_correctness_status=SEMANTIC_CORRECTNESS_NOT_EVALUATED,
            )

        verification = create_run_scoped_verification(
            selected=selected,
            tokenizer_artefact_hashes=renderer.tokenizer_artefact_hashes,
            measurement_timestamp=measurement_timestamp,
            container_sha=active_config.container_sha256,
            evidence_run_id=run_id,
            policy=probe_policy,
        )
        if not verification_matches_run(
            verification,
            evidence_run_id=run_id,
            model_repository=active_config.model_repository,
            immutable_revision=active_config.model_revision,
            container_sha=active_config.container_sha256,
            tokenizer_artefact_hashes=renderer.tokenizer_artefact_hashes,
            semantic_schema_hash=schema_hash,
            structured_decode_contract_hash=contract_hash,
            response_mode=selected.candidate_mode,
        ):
            rejections = ("run_scoped_verification_identity_mismatch",)
            _write_evidence_package(
                run_dir,
                status="BLOCKED",
                run_id=run_id,
                rejection_reasons=rejections,
                measurement_timestamp=measurement_timestamp,
                config=active_config,
                probe_results=probe_results,
                manifest_base={**manifest_base, "status": "BLOCKED", "rejection_reasons": list(rejections)},
            )
            return DFinalRunResult(
                status="BLOCKED",
                run_id=run_id,
                rejection_reasons=rejections,
                run_dir=str(run_dir),
                engine_started=engine_started,
                response_mode=None,
                accepted_count=0,
                rejected_after_attempts_count=0,
                rejected_non_retryable_count=0,
                semantic_correctness_status=SEMANTIC_CORRECTNESS_NOT_EVALUATED,
            )

        verified_renderer = RunScopedVerifiedRenderer(
            base_renderer=renderer,
            verification=verification,
        )
        if not verified_renderer.usable_for_run(
            evidence_run_id=run_id,
            model_repository=active_config.model_repository,
            immutable_revision=active_config.model_revision,
            container_sha=active_config.container_sha256,
            tokenizer_artefact_hashes=renderer.tokenizer_artefact_hashes,
            semantic_schema_hash=schema_hash,
            structured_decode_contract_hash=contract_hash,
            response_mode=selected.candidate_mode,
        ):
            rejections = ("verified_renderer_run_identity_mismatch",)
            _write_evidence_package(
                run_dir,
                status="BLOCKED",
                run_id=run_id,
                rejection_reasons=rejections,
                measurement_timestamp=measurement_timestamp,
                config=active_config,
                probe_results=probe_results,
                manifest_base={**manifest_base, "status": "BLOCKED", "rejection_reasons": list(rejections)},
            )
            return DFinalRunResult(
                status="BLOCKED",
                run_id=run_id,
                rejection_reasons=rejections,
                run_dir=str(run_dir),
                engine_started=engine_started,
                response_mode=None,
                accepted_count=0,
                rejected_after_attempts_count=0,
                rejected_non_retryable_count=0,
                semantic_correctness_status=SEMANTIC_CORRECTNESS_NOT_EVALUATED,
            )

        backend_identity = BackendIdentity(
            backend_identifier=runtime_config.backend_identifier,
            backend_configuration_hash=runtime_config.config_hash,
        )

        raw_attempt_rows: list[dict[str, Any]] = []
        ledger_rows: list[dict[str, Any]] = []
        accepted_rows: list[dict[str, Any]] = []
        record_result_rows: list[dict[str, Any]] = []
        accepted_count = 0
        rejected_after_attempts_count = 0
        rejected_non_retryable_count = 0
        final_rejections: list[str] = []

        for record, request in zip(records, pipeline_requests, strict=True):
            if record_generator is not None:
                pipeline_generator = _InjectedRecordGenerator(record_generator, record_id=record["record_id"])
            else:
                pipeline_generator = VllmPipelineGenerator(
                    backend=backend,
                    ordinal_base=100 + int(record["ordinal"]) * 10,
                )
            result = run_generation_pipeline(
                request,
                renderer=verified_renderer,
                generator=pipeline_generator,
                backend=backend_identity,
                structured_decode_readiness=structured_readiness,
                immutable_selection={
                    "model_repository": active_config.model_repository,
                    "immutable_revision": active_config.model_revision,
                },
                policy=generation_policy,
                structured_decode_contract=decode_contract,
                pipeline_contract=pipeline_contract,
            )
            for entry in result.attempt_entries:
                raw_attempt_rows.append(entry.to_dict())
                ledger_rows.append(entry.to_dict())
            record_result_rows.append(
                {
                    "record_id": record["record_id"],
                    "request_id": result.request_id,
                    "final_status": result.final_status,
                    "attempts_used": result.attempts_used,
                    "failure_categories": list(result.failure_categories),
                    "failure_reasons": list(result.failure_reasons),
                    "semantic_correctness_status": SEMANTIC_CORRECTNESS_NOT_EVALUATED,
                    "expected_structural_disposition": record.get("expected_structural_disposition"),
                }
            )
            if result.final_status == PipelineFinalStatus.ACCEPTED.value:
                accepted_count += 1
                if result.accepted_canonical_prediction is not None:
                    accepted_rows.append(result.accepted_canonical_prediction)
            elif result.final_status == PipelineFinalStatus.REJECTED_AFTER_ATTEMPTS.value:
                rejected_after_attempts_count += 1
                final_rejections.append(f"{record['record_id']}:rejected_after_attempts")
            else:
                rejected_non_retryable_count += 1
                final_rejections.append(f"{record['record_id']}:rejected_non_retryable")

        status = "PASS" if accepted_count == len(records) and not final_rejections else "BLOCKED"
        if accepted_count != len(records):
            final_rejections.append("not_all_records_accepted")

        _write_evidence_package(
            run_dir,
            status=status,
            run_id=run_id,
            rejection_reasons=tuple(final_rejections),
            measurement_timestamp=measurement_timestamp,
            config=active_config,
            probe_results=probe_results,
            verification=verification,
            raw_attempt_rows=raw_attempt_rows,
            ledger_rows=ledger_rows,
            accepted_rows=accepted_rows,
            record_result_rows=record_result_rows,
            selected_mode=selected.candidate_mode,
            accepted_count=accepted_count,
            rejected_after_attempts_count=rejected_after_attempts_count,
            rejected_non_retryable_count=rejected_non_retryable_count,
            manifest_base={
                **manifest_base,
                "status": status,
                "response_mode": selected.candidate_mode,
                "rejection_reasons": list(final_rejections),
                "generation_settings": AUTHORITATIVE_GENERATION,
                "batch_size": AUTHORITATIVE_BATCH_SIZE,
                "engine_settings": AUTHORITATIVE_ENGINE,
            },
        )

        return DFinalRunResult(
            status=status,
            run_id=run_id,
            rejection_reasons=tuple(final_rejections),
            run_dir=str(run_dir),
            engine_started=engine_started,
            response_mode=selected.candidate_mode,
            accepted_count=accepted_count,
            rejected_after_attempts_count=rejected_after_attempts_count,
            rejected_non_retryable_count=rejected_non_retryable_count,
            semantic_correctness_status=SEMANTIC_CORRECTNESS_NOT_EVALUATED,
        )
    except Exception as exc:  # noqa: BLE001
        # Unexpected exception boundary: emit honest BLOCKED evidence package.
        reason = f"unexpected_runner_exception:{type(exc).__name__}"
        _write_evidence_package(
            run_dir,
            status="BLOCKED",
            run_id=run_id,
            rejection_reasons=(reason,),
            measurement_timestamp=measurement_timestamp,
            config=active_config,
            probe_results=probe_results,
            selected_mode=None,
            manifest_base={**manifest_base, "status": "BLOCKED", "rejection_reasons": [reason]},
        )
        return DFinalRunResult(
            status="BLOCKED",
            run_id=run_id,
            rejection_reasons=(reason,),
            run_dir=str(run_dir),
            engine_started=engine_started,
            response_mode=None,
            accepted_count=0,
            rejected_after_attempts_count=0,
            rejected_non_retryable_count=0,
            semantic_correctness_status=SEMANTIC_CORRECTNESS_NOT_EVALUATED,
        )
    finally:
        if engine_started:
            backend.close()


class _InjectedRecordGenerator:
    def __init__(self, factory: Callable[..., str], *, record_id: str) -> None:
        self._factory = factory
        self._record_id = record_id
        self.calls = 0

    def generate(
        self,
        *,
        rendered_prompt: str,
        attempt_index: int,
        caller_request_id: str,
    ) -> Any:
        from ambiguity_manager.model.generation_pipeline import GeneratorOutput

        self.calls += 1
        raw_output = self._factory(
            record_id=self._record_id,
            rendered_prompt=rendered_prompt,
            attempt_index=attempt_index,
            caller_request_id=caller_request_id,
        )
        return GeneratorOutput(raw_output=raw_output, generation_status="success", finish_reason="stop")
