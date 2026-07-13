"""Run-scoped response-mode probe policy and verification for T12 Stage D-Final."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.parser import extract_and_repair_json
from ambiguity_manager.model.prediction_contract import (
    SemanticPayloadError,
    model_semantic_output_schema_hash,
    validate_semantic_payload,
)
from ambiguity_manager.model.structured_decode import (
    StructuredDecodeContract,
    load_structured_decode_contract,
    structured_decode_contract_hash,
)

DEFAULT_POLICY_REL = Path("configs") / "model" / "t12_response_mode_probe_policy.json"
THINKING_MARKERS = ("<think>", "</think>")
VERIFIED_FOR_RUN = "verified_for_run"


class ResponseModeProbeError(Exception):
    """Raised when response-mode probe policy validation fails."""


@dataclass(frozen=True)
class ResponseModeProbePolicy:
    schema_version: str
    policy_version: str
    candidate_order: tuple[str, ...]
    synthetic_probe_command: str
    semantic_schema_hash: str
    structured_decode_contract_hash: str
    response_mode_verification_scope: str
    semantic_schema_validation_role: str
    semantic_schema_enforcement_owner: str
    generation: dict[str, Any]
    cleanliness_checks: dict[str, Any]
    structural_checks: dict[str, Any]
    selection_rule: str
    tie_break_rule: str
    verification_status_value: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "candidate_order": list(self.candidate_order),
            "synthetic_probe_command": self.synthetic_probe_command,
            "semantic_schema_hash": self.semantic_schema_hash,
            "structured_decode_contract_hash": self.structured_decode_contract_hash,
            "response_mode_verification_scope": self.response_mode_verification_scope,
            "semantic_schema_validation_role": self.semantic_schema_validation_role,
            "semantic_schema_enforcement_owner": self.semantic_schema_enforcement_owner,
            "generation": dict(self.generation),
            "cleanliness_checks": dict(self.cleanliness_checks),
            "structural_checks": dict(self.structural_checks),
            "selection_rule": self.selection_rule,
            "tie_break_rule": self.tie_break_rule,
            "verification_status_value": self.verification_status_value,
        }


@dataclass(frozen=True)
class ProbeCandidateResult:
    candidate_mode: str
    rendered_prompt_hash: str
    raw_output: str
    raw_output_hash: str
    generation_status: str
    prompt_tokens: int | None
    completion_tokens: int | None
    direct_json_parse_status: str
    raw_object_status: str
    local_repair_attempts: int
    local_repair_log: tuple[str, ...]
    semantic_schema_status: str
    semantic_schema_error: str | None
    thinking_markers_present: bool
    prose_before_json: bool
    prose_after_json: bool
    engine_request_id: str | None
    finish_reason: str | None
    unconstrained_fallback_indicated: bool
    structured_decode_metadata: dict[str, Any] | None
    model_repository: str
    model_revision: str
    schema_hash: str
    contract_hash: str
    passed: bool
    failure_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_mode": self.candidate_mode,
            "rendered_prompt_hash": self.rendered_prompt_hash,
            "raw_output": self.raw_output,
            "raw_output_hash": self.raw_output_hash,
            "generation_status": self.generation_status,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "direct_json_parse_status": self.direct_json_parse_status,
            "raw_object_status": self.raw_object_status,
            "local_repair_attempts": self.local_repair_attempts,
            "local_repair_log": list(self.local_repair_log),
            "semantic_schema_status": self.semantic_schema_status,
            "semantic_schema_error": self.semantic_schema_error,
            "thinking_markers_present": self.thinking_markers_present,
            "prose_before_json": self.prose_before_json,
            "prose_after_json": self.prose_after_json,
            "engine_request_id": self.engine_request_id,
            "finish_reason": self.finish_reason,
            "unconstrained_fallback_indicated": self.unconstrained_fallback_indicated,
            "structured_decode_metadata": self.structured_decode_metadata,
            "model_repository": self.model_repository,
            "model_revision": self.model_revision,
            "schema_hash": self.schema_hash,
            "contract_hash": self.contract_hash,
            "passed": self.passed,
            "failure_reasons": list(self.failure_reasons),
        }


@dataclass(frozen=True)
class RunScopedResponseModeVerification:
    model_repository: str
    immutable_revision: str
    tokenizer_artefact_hashes: dict[str, str]
    response_mode: str
    verification_scope: str
    semantic_schema_validation_role: str
    probe_semantic_schema_status: str
    semantic_schema_required_for_mode_selection: bool
    final_semantic_schema_enforcement_owner: str
    rendered_prompt_hash: str
    probe_output_hash: str
    semantic_schema_hash: str
    structured_decode_contract_hash: str
    probe_checks: dict[str, Any]
    measurement_timestamp: str
    container_sha: str
    evidence_run_id: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_repository": self.model_repository,
            "immutable_revision": self.immutable_revision,
            "tokenizer_artefact_hashes": dict(self.tokenizer_artefact_hashes),
            "response_mode": self.response_mode,
            "verification_scope": self.verification_scope,
            "semantic_schema_validation_role": self.semantic_schema_validation_role,
            "probe_semantic_schema_status": self.probe_semantic_schema_status,
            "semantic_schema_required_for_mode_selection": self.semantic_schema_required_for_mode_selection,
            "final_semantic_schema_enforcement_owner": self.final_semantic_schema_enforcement_owner,
            "rendered_prompt_hash": self.rendered_prompt_hash,
            "probe_output_hash": self.probe_output_hash,
            "semantic_schema_hash": self.semantic_schema_hash,
            "structured_decode_contract_hash": self.structured_decode_contract_hash,
            "probe_checks": dict(self.probe_checks),
            "measurement_timestamp": self.measurement_timestamp,
            "container_sha": self.container_sha,
            "evidence_run_id": self.evidence_run_id,
            "status": self.status,
        }


def validate_probe_policy(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != "1.0.0":
        errors.append("probe_policy.schema_version must be 1.0.0")
    order = payload.get("candidate_order")
    if order != ["default", "enable_thinking_false"]:
        errors.append("probe_policy.candidate_order must be ['default', 'enable_thinking_false']")
    if not payload.get("synthetic_probe_command"):
        errors.append("probe_policy.synthetic_probe_command is required")
    if payload.get("semantic_schema_hash") != model_semantic_output_schema_hash():
        errors.append("probe_policy.semantic_schema_hash mismatch")
    if (
        payload.get("response_mode_verification_scope")
        != "clean_single_json_object_with_verified_structured_decode"
    ):
        errors.append("probe_policy.response_mode_verification_scope mismatch")
    if payload.get("semantic_schema_validation_role") != "diagnostic_only_for_response_mode_selection":
        errors.append("probe_policy.semantic_schema_validation_role mismatch")
    if payload.get("semantic_schema_enforcement_owner") != "d1c1_generation_pipeline":
        errors.append("probe_policy.semantic_schema_enforcement_owner mismatch")
    return errors


def load_response_mode_probe_policy(path: Path | str | None = None) -> ResponseModeProbePolicy:
    from ambiguity_manager.paths import repo_root

    target = Path(path) if path is not None else repo_root() / DEFAULT_POLICY_REL
    payload = json.loads(target.read_text(encoding="utf-8"))
    errors = validate_probe_policy(payload)
    if errors:
        raise ResponseModeProbeError("; ".join(errors))
    contract = load_structured_decode_contract()
    expected_contract_hash = structured_decode_contract_hash(contract)
    if payload.get("structured_decode_contract_hash") != expected_contract_hash:
        raise ResponseModeProbeError("probe_policy.structured_decode_contract_hash mismatch")
    return ResponseModeProbePolicy(
        schema_version=str(payload["schema_version"]),
        policy_version=str(payload["policy_version"]),
        candidate_order=tuple(str(item) for item in payload["candidate_order"]),
        synthetic_probe_command=str(payload["synthetic_probe_command"]),
        semantic_schema_hash=str(payload["semantic_schema_hash"]),
        structured_decode_contract_hash=str(payload["structured_decode_contract_hash"]),
        response_mode_verification_scope=str(payload["response_mode_verification_scope"]),
        semantic_schema_validation_role=str(payload["semantic_schema_validation_role"]),
        semantic_schema_enforcement_owner=str(payload["semantic_schema_enforcement_owner"]),
        generation=dict(payload["generation"]),
        cleanliness_checks=dict(payload["cleanliness_checks"]),
        structural_checks=dict(payload["structural_checks"]),
        selection_rule=str(payload["selection_rule"]),
        tie_break_rule=str(payload["tie_break_rule"]),
        verification_status_value=str(payload["verification_status_value"]),
    )


def detect_thinking_markers(raw_output: str) -> bool:
    return any(marker in raw_output for marker in THINKING_MARKERS)


def detect_prose_contamination(raw_output: str) -> tuple[bool, bool]:
    stripped = raw_output.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return True, True
    return bool(stripped[:start].strip()), bool(stripped[end + 1 :].strip())


def _strict_direct_json_parse(raw_output: str) -> tuple[str, str, dict[str, Any] | None]:
    stripped = raw_output.strip()
    if not stripped:
        return "failed", "empty", None
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        return "failed", "invalid_json", None
    if not isinstance(value, dict):
        return "success", "not_single_object", None
    return "success", "single_object", value


def evaluate_probe_candidate(
    *,
    candidate_mode: str,
    rendered_prompt_hash: str,
    raw_output: str,
    generation_status: str,
    finish_reason: str | None,
    engine_request_id: str | None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    model_repository: str,
    model_revision: str,
    schema_hash: str,
    contract_hash: str,
    policy: ResponseModeProbePolicy,
    contract: StructuredDecodeContract,
    immutable: Any,
    structured_decode_metadata: dict[str, Any] | None = None,
    unconstrained_fallback_indicated: bool = False,
) -> ProbeCandidateResult:
    failures: list[str] = []
    raw_hash = sha256_hex(raw_output.encode("utf-8")) if raw_output else ""

    if generation_status != "success":
        failures.append(f"generation_status={generation_status!r}")
    required_finish_reason = policy.structural_checks.get("require_finish_reason")
    if required_finish_reason is not None and finish_reason != required_finish_reason:
        failures.append(f"finish_reason={finish_reason!r}")
    if policy.structural_checks.get("require_non_empty_raw_output") and not raw_output.strip():
        failures.append("empty_raw_output")

    thinking = detect_thinking_markers(raw_output)
    if policy.cleanliness_checks.get("reject_thinking_markers") and thinking:
        failures.append("thinking_markers_present")

    prose_before, prose_after = detect_prose_contamination(raw_output)
    if policy.cleanliness_checks.get("reject_prose_contamination"):
        if prose_before:
            failures.append("prose_before_json")
        if prose_after:
            failures.append("prose_after_json")

    direct_json_parse_status = "skipped"
    raw_object_status = "skipped"
    semantic_schema_status = "skipped"
    semantic_schema_error: str | None = None
    local_repair_attempts = 0
    local_repair_log: tuple[str, ...] = ()

    if raw_output.strip() and generation_status == "success":
        repair_result = extract_and_repair_json(raw_output)
        local_repair_attempts = repair_result.repair_attempts
        local_repair_log = tuple(repair_result.repair_log)

        direct_json_parse_status, raw_object_status, parsed_object = _strict_direct_json_parse(raw_output)

        if direct_json_parse_status != "success":
            failures.append("direct_json_parse_failed")
        elif raw_object_status != "single_object":
            failures.append(f"raw_object_status={raw_object_status!r}")
        elif local_repair_attempts > 0:
            failures.append("local_repair_required")
        else:
            try:
                validate_semantic_payload(parsed_object or {})
                semantic_schema_status = "valid"
            except SemanticPayloadError as exc:
                semantic_schema_status = "invalid"
                semantic_schema_error = str(exc)

    if policy.structural_checks.get("reject_unconstrained_fallback") and unconstrained_fallback_indicated:
        failures.append("unconstrained_fallback_indicated")

    if structured_decode_metadata is None and policy.structural_checks.get("reject_unconstrained_fallback"):
        failures.append("structured_decode_metadata_absent")
    elif structured_decode_metadata is not None:
        if structured_decode_metadata.get("contract_hash") != contract_hash:
            failures.append("structured_decode_contract_hash_mismatch")
        if structured_decode_metadata.get("schema_hash") != schema_hash:
            failures.append("structured_decode_schema_hash_mismatch")
        if structured_decode_metadata.get("completions_per_request") != 1:
            failures.append("structured_decode_completions_per_request_mismatch")
        if structured_decode_metadata.get("construction_status") != "constructed":
            failures.append("structured_decode_construction_not_constructed")
        detected_version = structured_decode_metadata.get("detected_vllm_version")
        required_version = structured_decode_metadata.get("required_vllm_version")
        if detected_version != required_version:
            failures.append("structured_decode_vllm_version_mismatch")

    if policy.structural_checks.get("require_identity_match"):
        if schema_hash != policy.semantic_schema_hash:
            failures.append("schema_hash_mismatch")
        if contract_hash != policy.structured_decode_contract_hash:
            failures.append("contract_hash_mismatch")
        expected_schema = model_semantic_output_schema_hash()
        if schema_hash != expected_schema:
            failures.append("model_schema_identity_mismatch")

    if model_repository and model_revision:
        if immutable is None:
            failures.append("immutable_selection_missing")
        else:
            if model_repository != getattr(immutable, "model_repository", None):
                failures.append("model_repository_mismatch")
            if model_revision != getattr(immutable, "model_revision", None):
                failures.append("model_revision_mismatch")

    passed = not failures
    return ProbeCandidateResult(
        candidate_mode=candidate_mode,
        rendered_prompt_hash=rendered_prompt_hash,
        raw_output=raw_output,
        raw_output_hash=raw_hash,
        generation_status=generation_status,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        direct_json_parse_status=direct_json_parse_status,
        raw_object_status=raw_object_status,
        local_repair_attempts=local_repair_attempts,
        local_repair_log=local_repair_log,
        semantic_schema_status=semantic_schema_status,
        semantic_schema_error=semantic_schema_error,
        thinking_markers_present=thinking,
        prose_before_json=prose_before,
        prose_after_json=prose_after,
        engine_request_id=engine_request_id,
        finish_reason=finish_reason,
        unconstrained_fallback_indicated=unconstrained_fallback_indicated,
        structured_decode_metadata=structured_decode_metadata,
        model_repository=model_repository,
        model_revision=model_revision,
        schema_hash=schema_hash,
        contract_hash=contract_hash,
        passed=passed,
        failure_reasons=tuple(failures),
    )


def select_response_mode(
    candidate_results: list[ProbeCandidateResult],
    *,
    policy: ResponseModeProbePolicy,
) -> ProbeCandidateResult | None:
    by_mode = {item.candidate_mode: item for item in candidate_results}
    for mode in policy.candidate_order:
        result = by_mode.get(mode)
        if result is not None and result.passed:
            return result
    return None


def create_run_scoped_verification(
    *,
    selected: ProbeCandidateResult,
    tokenizer_artefact_hashes: dict[str, str],
    measurement_timestamp: str,
    container_sha: str,
    evidence_run_id: str,
    policy: ResponseModeProbePolicy,
) -> RunScopedResponseModeVerification:
    return RunScopedResponseModeVerification(
        model_repository=selected.model_repository,
        immutable_revision=selected.model_revision,
        tokenizer_artefact_hashes=dict(tokenizer_artefact_hashes),
        response_mode=selected.candidate_mode,
        verification_scope=policy.response_mode_verification_scope,
        semantic_schema_validation_role=policy.semantic_schema_validation_role,
        probe_semantic_schema_status=selected.semantic_schema_status,
        semantic_schema_required_for_mode_selection=False,
        final_semantic_schema_enforcement_owner=policy.semantic_schema_enforcement_owner,
        rendered_prompt_hash=selected.rendered_prompt_hash,
        probe_output_hash=selected.raw_output_hash,
        semantic_schema_hash=selected.schema_hash,
        structured_decode_contract_hash=selected.contract_hash,
        probe_checks={
            "generation_status": selected.generation_status,
            "finish_reason": selected.finish_reason,
            "prompt_tokens": selected.prompt_tokens,
            "completion_tokens": selected.completion_tokens,
            "direct_json_parse_status": selected.direct_json_parse_status,
            "raw_object_status": selected.raw_object_status,
            "local_repair_attempts": selected.local_repair_attempts,
            "local_repair_log": list(selected.local_repair_log),
            "semantic_schema_status": selected.semantic_schema_status,
            "semantic_schema_error": selected.semantic_schema_error,
            "thinking_markers_present": selected.thinking_markers_present,
            "prose_before_json": selected.prose_before_json,
            "prose_after_json": selected.prose_after_json,
            "unconstrained_fallback_indicated": selected.unconstrained_fallback_indicated,
            "structured_decode_metadata": selected.structured_decode_metadata,
            "failure_reasons": list(selected.failure_reasons),
        },
        measurement_timestamp=measurement_timestamp,
        container_sha=container_sha,
        evidence_run_id=evidence_run_id,
        status=policy.verification_status_value,
    )


def verification_matches_run(
    verification: RunScopedResponseModeVerification,
    *,
    evidence_run_id: str,
    model_repository: str,
    immutable_revision: str,
    container_sha: str,
    tokenizer_artefact_hashes: dict[str, str],
    semantic_schema_hash: str,
    structured_decode_contract_hash: str,
    response_mode: str,
) -> bool:
    if verification.status != VERIFIED_FOR_RUN:
        return False
    if verification.evidence_run_id != evidence_run_id:
        return False
    if verification.model_repository != model_repository:
        return False
    if verification.immutable_revision != immutable_revision:
        return False
    if verification.container_sha != container_sha:
        return False
    if verification.tokenizer_artefact_hashes != tokenizer_artefact_hashes:
        return False
    if verification.semantic_schema_hash != semantic_schema_hash:
        return False
    if verification.structured_decode_contract_hash != structured_decode_contract_hash:
        return False
    if verification.response_mode != response_mode:
        return False
    return True
