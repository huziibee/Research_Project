"""Model-neutral bounded generation pipeline for T12 Stage D1C1."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.attempt_evidence import (
    AttemptDisposition,
    AttemptEvidenceEntry,
    AttemptEvidenceLedger,
    AttemptKind,
    defensive_copy_metadata,
)
from ambiguity_manager.model.generation_policy import GenerationPolicy, load_generation_policy
from ambiguity_manager.model.integrity import (
    REQUIRED_DECLARATION_FIELDS,
    count_unsupported_commitments,
)
from ambiguity_manager.model.parser import extract_and_repair_json
from ambiguity_manager.model.prediction_contract import (
    PredictionAssemblyError,
    PredictionProvenancePolicy,
    PredictionRequestContext,
    PredictionRuntimeMetadata,
    SemanticPayloadError,
    assemble_prediction_record,
    model_semantic_output_schema_hash,
    validate_semantic_payload,
)
from ambiguity_manager.model.prompt_builder import (
    PromptBuildRequest,
    build_prompt_messages,
    build_system_message,
    compute_prompt_hash,
)
from ambiguity_manager.model.repair_prompt import (
    RepairPromptRequest,
    build_repair_messages,
    build_repair_prompt,
    load_pipeline_contract,
)
from ambiguity_manager.model.response_mode import ResponseModeStatus
from ambiguity_manager.model.structured_decode import (
    StructuredDecodeContract,
    StructuredDecodeMetadata,
    load_structured_decode_contract,
    structured_decode_contract_hash,
)
from ambiguity_manager.schema.v2.records import LabelEligibility
from ambiguity_manager.schema.v2.validation import validate_canonical_record_v2

ATTEMPT_KINDS: tuple[str, ...] = ("initial", "regeneration", "regeneration")
DEFAULT_PIPELINE_CONTRACT_REL = Path("configs") / "model" / "t12_generation_pipeline_contract.json"
IMMUTABLE_SELECTION_REL = Path("configs") / "model" / "immutable_selection.json"
SEMANTIC_CORRECTNESS_NOT_EVALUATED = "not_evaluated"
MAX_SANITIZED_ERROR_MESSAGE_CHARS = 500

REPAIRABLE_GENERATOR_ERROR_TYPES: frozenset[str] = frozenset(
    {"transient_output_production_failure"}
)

NON_RETRYABLE_GENERATOR_ERROR_TYPES: frozenset[str] = frozenset(
    {
        "backend_dependency_failure",
        "backend_configuration_failure",
        "backend_startup_failure",
        "engine_failure",
        "immutable_model_mismatch",
        "structured_decode_failure",
        "response_mode_failure",
        "contract_mismatch",
        "schema_mismatch",
        "unknown_exception",
        "unclassified_generator_error",
        "programming_error",
        "policy_corruption",
    }
)


class PipelineFinalStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED_AFTER_ATTEMPTS = "rejected_after_attempts"
    REJECTED_NON_RETRYABLE = "rejected_non_retryable"


class FailureCategory(StrEnum):
    INVALID_CALLER_INPUT = "invalid_caller_input"
    NON_SYNTHETIC_INPUT = "non_synthetic_input"
    RESPONSE_MODE_UNVERIFIED = "response_mode_unverified"
    RESPONSE_MODE_IDENTITY_MISMATCH = "response_mode_identity_mismatch"
    STRUCTURED_DECODE_METADATA_ABSENT = "structured_decode_metadata_absent"
    STRUCTURED_DECODE_CONTRACT_MISMATCH = "structured_decode_contract_mismatch"
    STRUCTURED_DECODE_SCHEMA_MISMATCH = "structured_decode_schema_mismatch"
    STRUCTURED_DECODE_CONSTRUCTION_FAILED = "structured_decode_construction_failed"
    UNCONSTRAINED_FALLBACK_INDICATED = "unconstrained_fallback_indicated"
    MULTIPLE_COMPLETIONS_PERMITTED = "multiple_completions_permitted"
    BACKEND_DEPENDENCY_FAILURE = "backend_dependency_failure"
    BACKEND_CONFIGURATION_FAILURE = "backend_configuration_failure"
    BACKEND_STARTUP_FAILURE = "backend_startup_failure"
    MODEL_REVISION_MISMATCH = "model_revision_mismatch"
    POLICY_CONFIGURATION_CORRUPTION = "policy_configuration_corruption"
    JSON_EXTRACTION_FAILURE = "json_extraction_failure"
    JSON_PARSE_FAILURE = "json_parse_failure"
    NON_OBJECT_JSON = "non_object_json"
    SEMANTIC_SCHEMA_VALIDATION_FAILURE = "semantic_schema_validation_failure"
    CANONICAL_ASSEMBLY_FAILURE = "canonical_assembly_failure"
    UNSUPPORTED_SILENT_COMMITMENT = "unsupported_silent_commitment"
    EMPTY_GENERATION_OUTPUT = "empty_generation_output"
    TRANSIENT_OUTPUT_PRODUCTION_FAILURE = "transient_output_production_failure"
    UNKNOWN_EXCEPTION = "unknown_exception"
    UNCLASSIFIED_GENERATOR_ERROR = "unclassified_generator_error"
    ENGINE_FAILURE = "engine_failure"
    INTEGRITY_CONTEXT_MISSING = "integrity_context_missing"
    INTEGRITY_CONTEXT_MALFORMED = "integrity_context_malformed"


REPAIRABLE_FAILURES: frozenset[FailureCategory] = frozenset(
    {
        FailureCategory.JSON_EXTRACTION_FAILURE,
        FailureCategory.JSON_PARSE_FAILURE,
        FailureCategory.NON_OBJECT_JSON,
        FailureCategory.SEMANTIC_SCHEMA_VALIDATION_FAILURE,
        FailureCategory.CANONICAL_ASSEMBLY_FAILURE,
        FailureCategory.UNSUPPORTED_SILENT_COMMITMENT,
        FailureCategory.EMPTY_GENERATION_OUTPUT,
        FailureCategory.TRANSIENT_OUTPUT_PRODUCTION_FAILURE,
    }
)


class GenerationPipelineError(Exception):
    """Base error for generation pipeline operations."""


@dataclass(frozen=True)
class PipelineIntegrityContext:
    """Immutable caller-supplied integrity context for commitment checks."""

    _canonical_json: str

    def to_fixture_dict(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    def hash(self) -> str:
        return sha256_hex(self._canonical_json.encode("utf-8"))

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "PipelineIntegrityContext":
        normalized = _normalize_integrity_mapping(raw)
        canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return cls(_canonical_json=canonical)


def _empty_support_declarations() -> dict[str, Any]:
    return {
        "supported_objects": [],
        "supported_locations": [],
        "supported_quantities": [],
        "supported_temporal_values": [],
        "supported_capabilities": [],
        "supported_safety_facts": [],
        "valid_evidence_references": [],
        "critical_slots": [],
        "expected_route_pressure": "execute",
    }


def empty_integrity_context() -> PipelineIntegrityContext:
    """Explicit integrity context with no supported commitments."""
    return PipelineIntegrityContext.from_mapping({"support_declarations": _empty_support_declarations()})


def _normalize_support_declarations(decl: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field in REQUIRED_DECLARATION_FIELDS:
        value = decl.get(field)
        if field == "expected_route_pressure":
            normalized[field] = str(value) if value is not None else ""
        elif value is None:
            normalized[field] = []
        elif isinstance(value, list):
            normalized[field] = sorted(str(item) for item in value)
        else:
            raise TypeError(f"support_declarations.{field} must be a list or string")
    return normalized


def _normalize_integrity_mapping(raw: dict[str, Any]) -> dict[str, Any]:
    declarations = raw.get("support_declarations")
    if not isinstance(declarations, dict):
        raise TypeError("support_declarations must be an object")
    normalized: dict[str, Any] = {
        "support_declarations": _normalize_support_declarations(declarations),
    }
    for optional_field in (
        "fixture_id",
        "command",
        "scene_context",
        "capability_context",
    ):
        if optional_field in raw:
            value = raw[optional_field]
            if value is not None:
                normalized[optional_field] = str(value)
    if "dialogue_history" in raw:
        history = raw["dialogue_history"]
        if history is not None:
            if not isinstance(history, list) or not all(isinstance(item, str) for item in history):
                raise TypeError("dialogue_history must be a list of strings")
            normalized["dialogue_history"] = list(history)
    return normalized


def validate_integrity_context(raw: PipelineIntegrityContext | dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    if raw is None:
        errors.append("integrity_context is mandatory")
        return errors
    if isinstance(raw, PipelineIntegrityContext):
        return errors
    if not isinstance(raw, dict):
        errors.append("integrity_context must be an object")
        return errors
    declarations = raw.get("support_declarations")
    if not isinstance(declarations, dict):
        errors.append("support_declarations is required")
        return errors
    for field in REQUIRED_DECLARATION_FIELDS:
        if field not in declarations:
            errors.append(f"support_declarations.{field} is required")
        elif field != "expected_route_pressure":
            value = declarations.get(field)
            if value is not None and not isinstance(value, list):
                errors.append(f"support_declarations.{field} must be a list")
        else:
            value = declarations.get(field)
            if value is not None and not isinstance(value, str):
                errors.append("support_declarations.expected_route_pressure must be a string")
    try:
        _normalize_integrity_mapping(raw)
    except TypeError as exc:
        errors.append(str(exc))
    return errors


def _coerce_integrity_context(
    raw: PipelineIntegrityContext | dict[str, Any],
) -> PipelineIntegrityContext:
    if isinstance(raw, PipelineIntegrityContext):
        return raw
    return PipelineIntegrityContext.from_mapping(raw)


def _sanitize_error_message(message: str) -> str:
    lines = [
        line
        for line in message.splitlines()
        if not line.strip().startswith('File "') and "Traceback (most recent call last)" not in line
    ]
    compact = " ".join(line.strip() for line in lines if line.strip())
    if not compact:
        compact = message.strip()
    if len(compact) > MAX_SANITIZED_ERROR_MESSAGE_CHARS:
        return compact[:MAX_SANITIZED_ERROR_MESSAGE_CHARS]
    return compact


@dataclass(frozen=True)
class GenerationPipelineRequest:
    caller_request_id: str
    synthetic: bool
    command: str
    label_eligibility: LabelEligibility
    provenance_policy: PredictionProvenancePolicy
    source_dataset: str
    integrity_context: PipelineIntegrityContext
    scene_context: str | None = None
    dialogue_history: list[str] = field(default_factory=list)
    capability_context: str | None = None
    source_id: str | None = None
    original_split: str | None = None
    group_id: str | None = None
    mapping_version: str | None = None
    source_license: str | None = None
    mapping_notes: str | None = None
    source_metadata: dict[str, Any] | None = None
    generation_seed: int | None = None
    container_sha: str | None = None


@dataclass(frozen=True)
class GenerationReadyPromptEnvelope:
    rendered_prompt_text: str
    abstract_message_hash: str
    rendered_prompt_hash: str
    model_repository: str
    immutable_model_revision: str
    response_mode_status: str
    response_mode_method_identity: str
    renderer_identity: str
    renderer_version: str


@dataclass(frozen=True)
class StructuredDecodeReadiness:
    metadata: StructuredDecodeMetadata
    unconstrained_fallback_indicated: bool = False
    lossy_adaptation_indicated: bool = False


@dataclass(frozen=True)
class BackendIdentity:
    backend_identifier: str
    backend_configuration_hash: str


@dataclass(frozen=True)
class GeneratorOutput:
    raw_output: str
    generation_status: str = "success"
    generation_error_type: str | None = None
    generation_error_message: str | None = None
    engine_request_id: str | None = None
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    runtime_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationPipelineResult:
    request_id: str
    final_status: str
    accepted_canonical_prediction: dict[str, Any] | None
    attempt_entries: tuple[AttemptEvidenceEntry, ...]
    attempts_used: int
    attempts_exhausted: bool
    failure_categories: tuple[str, ...]
    failure_reasons: tuple[str, ...]
    semantic_schema_hash: str
    structured_decode_contract_hash: str
    caller_command_hash: str
    integrity_context_hash: str
    accepted_raw_attempt_index: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "final_status": self.final_status,
            "accepted_canonical_prediction": self.accepted_canonical_prediction,
            "attempt_entries": [entry.to_dict() for entry in self.attempt_entries],
            "attempts_used": self.attempts_used,
            "attempts_exhausted": self.attempts_exhausted,
            "failure_categories": list(self.failure_categories),
            "failure_reasons": list(self.failure_reasons),
            "semantic_schema_hash": self.semantic_schema_hash,
            "structured_decode_contract_hash": self.structured_decode_contract_hash,
            "caller_command_hash": self.caller_command_hash,
            "integrity_context_hash": self.integrity_context_hash,
            "accepted_raw_attempt_index": self.accepted_raw_attempt_index,
        }


class GenerationReadyRenderer(Protocol):
    def render(self, messages: list[dict[str, str]]) -> GenerationReadyPromptEnvelope:
        ...


class GenerationAttemptGenerator(Protocol):
    def generate(
        self,
        *,
        rendered_prompt: str,
        attempt_index: int,
        caller_request_id: str,
    ) -> GeneratorOutput:
        ...


def _load_immutable_selection() -> dict[str, str]:
    from ambiguity_manager.paths import repo_root

    payload = json.loads((repo_root() / IMMUTABLE_SELECTION_REL).read_text(encoding="utf-8"))
    return {
        "model_repository": str(payload["model_repository"]),
        "immutable_revision": str(payload["model_revision"]),
    }


def validate_pipeline_request(request: GenerationPipelineRequest) -> list[str]:
    errors: list[str] = []
    if not request.caller_request_id or not request.caller_request_id.strip():
        errors.append("caller_request_id must be non-empty")
    if not request.command or not request.command.strip():
        errors.append("command must be non-empty")
    if not request.synthetic:
        errors.append("synthetic marker must be true")
    if request.label_eligibility is None:
        errors.append("label_eligibility is mandatory")
    if request.provenance_policy is None:
        errors.append("provenance_policy is mandatory")
    errors.extend(validate_integrity_context(request.integrity_context))
    return errors


def verify_generation_ready_envelope(
    envelope: GenerationReadyPromptEnvelope,
    *,
    immutable_selection: dict[str, str] | None = None,
) -> list[tuple[FailureCategory, str]]:
    failures: list[tuple[FailureCategory, str]] = []
    selection = immutable_selection or _load_immutable_selection()
    if envelope.response_mode_status != ResponseModeStatus.VERIFIED.value:
        failures.append(
            (
                FailureCategory.RESPONSE_MODE_UNVERIFIED,
                f"response_mode_status={envelope.response_mode_status!r}",
            )
        )
    if envelope.model_repository != selection["model_repository"]:
        failures.append(
            (
                FailureCategory.RESPONSE_MODE_IDENTITY_MISMATCH,
                f"model_repository mismatch: {envelope.model_repository!r}",
            )
        )
    if envelope.immutable_model_revision != selection["immutable_revision"]:
        failures.append(
            (
                FailureCategory.MODEL_REVISION_MISMATCH,
                f"immutable_revision mismatch: {envelope.immutable_model_revision!r}",
            )
        )
    if not envelope.rendered_prompt_text or not envelope.rendered_prompt_text.strip():
        failures.append(
            (FailureCategory.INVALID_CALLER_INPUT, "rendered_prompt_text is empty")
        )
    if not envelope.abstract_message_hash or len(envelope.abstract_message_hash) != 64:
        failures.append(
            (FailureCategory.INVALID_CALLER_INPUT, "abstract_message_hash is missing or invalid")
        )
    if not envelope.rendered_prompt_hash or len(envelope.rendered_prompt_hash) != 64:
        failures.append(
            (FailureCategory.INVALID_CALLER_INPUT, "rendered_prompt_hash is missing or invalid")
        )
    return failures


def verify_structured_decode_readiness(
    readiness: StructuredDecodeReadiness | None,
    contract: StructuredDecodeContract,
) -> list[tuple[FailureCategory, str]]:
    failures: list[tuple[FailureCategory, str]] = []
    if readiness is None:
        failures.append(
            (FailureCategory.STRUCTURED_DECODE_METADATA_ABSENT, "readiness metadata absent")
        )
        return failures

    metadata = readiness.metadata
    expected_contract_hash = structured_decode_contract_hash(contract)
    if metadata.contract_hash != expected_contract_hash:
        failures.append(
            (
                FailureCategory.STRUCTURED_DECODE_CONTRACT_MISMATCH,
                f"contract_hash mismatch: {metadata.contract_hash!r}",
            )
        )
    if metadata.schema_hash != contract.semantic_schema_sha256:
        failures.append(
            (
                FailureCategory.STRUCTURED_DECODE_SCHEMA_MISMATCH,
                f"schema_hash mismatch: {metadata.schema_hash!r}",
            )
        )
    if metadata.construction_status != "constructed":
        failures.append(
            (
                FailureCategory.STRUCTURED_DECODE_CONSTRUCTION_FAILED,
                f"construction_status={metadata.construction_status!r}",
            )
        )
    if metadata.completions_per_request != 1:
        failures.append(
            (
                FailureCategory.MULTIPLE_COMPLETIONS_PERMITTED,
                f"completions_per_request={metadata.completions_per_request}",
            )
        )
    if readiness.unconstrained_fallback_indicated or contract.unconstrained_fallback_permitted:
        failures.append(
            (FailureCategory.UNCONSTRAINED_FALLBACK_INDICATED, "unconstrained fallback indicated")
        )
    if readiness.lossy_adaptation_indicated or contract.lossy_schema_adaptation_permitted:
        failures.append(
            (
                FailureCategory.STRUCTURED_DECODE_CONSTRUCTION_FAILED,
                "lossy schema adaptation indicated",
            )
        )
    return failures


def _prompt_build_request(request: GenerationPipelineRequest) -> PromptBuildRequest:
    return PromptBuildRequest(
        command=request.command,
        scene_context=request.scene_context,
        dialogue_history=list(request.dialogue_history),
        capability_context=request.capability_context,
    )


def _prediction_request_context(request: GenerationPipelineRequest) -> PredictionRequestContext:
    return PredictionRequestContext(
        request_id=request.caller_request_id,
        source_dataset=request.source_dataset,
        command=request.command,
        label_eligibility=request.label_eligibility,
        scene_context=request.scene_context,
        dialogue_history=list(request.dialogue_history),
        capability_context=request.capability_context,
        source_id=request.source_id,
        original_split=request.original_split,
        group_id=request.group_id,
        mapping_version=request.mapping_version,
        source_license=request.source_license,
        mapping_notes=request.mapping_notes,
        source_metadata=copy.deepcopy(request.source_metadata),
    )


def _compute_message_hash(messages: list[dict[str, str]]) -> str:
    payload = [{"role": item["role"], "content": item["content"]} for item in messages]
    return sha256_hex(canonical_json_bytes({"messages": payload}))


def _classify_parse_failures(parse_result: Any) -> tuple[FailureCategory, str]:
    if parse_result.extracted_json_text is None:
        return FailureCategory.JSON_EXTRACTION_FAILURE, "json extraction failed"
    try:
        import json as json_module

        value = json_module.loads(parse_result.extracted_json_text)
    except json.JSONDecodeError as exc:
        return FailureCategory.JSON_PARSE_FAILURE, str(exc)
    if not isinstance(value, dict):
        return FailureCategory.NON_OBJECT_JSON, "parsed JSON is not an object"
    return FailureCategory.JSON_PARSE_FAILURE, "json parse failed"


def _classify_generator_failure(generator_output: GeneratorOutput) -> tuple[FailureCategory, str]:
    error_type = generator_output.generation_error_type or "unclassified_generator_error"
    message = _sanitize_error_message(
        generator_output.generation_error_message or error_type
    )
    if error_type in REPAIRABLE_GENERATOR_ERROR_TYPES:
        return FailureCategory.TRANSIENT_OUTPUT_PRODUCTION_FAILURE, message
    if error_type in NON_RETRYABLE_GENERATOR_ERROR_TYPES:
        try:
            return FailureCategory(error_type), message
        except ValueError:
            return FailureCategory.UNCLASSIFIED_GENERATOR_ERROR, message
    if error_type == FailureCategory.BACKEND_DEPENDENCY_FAILURE.value:
        return FailureCategory.BACKEND_DEPENDENCY_FAILURE, message
    if error_type == FailureCategory.BACKEND_CONFIGURATION_FAILURE.value:
        return FailureCategory.BACKEND_CONFIGURATION_FAILURE, message
    if error_type == FailureCategory.BACKEND_STARTUP_FAILURE.value:
        return FailureCategory.BACKEND_STARTUP_FAILURE, message
    if error_type == FailureCategory.ENGINE_FAILURE.value:
        return FailureCategory.ENGINE_FAILURE, message
    return FailureCategory.UNCLASSIFIED_GENERATOR_ERROR, message


def _process_attempt_output(
    *,
    request: GenerationPipelineRequest,
    integrity_context: PipelineIntegrityContext,
    generator_output: GeneratorOutput,
    envelope: GenerationReadyPromptEnvelope,
    prompt_hash: str,
) -> tuple[
    dict[str, Any] | None,
    list[tuple[FailureCategory, str]],
    dict[str, Any],
]:
    diagnostics: dict[str, Any] = {"integrity_context_hash": integrity_context.hash()}
    failures: list[tuple[FailureCategory, str]] = []

    raw_output = generator_output.raw_output
    diagnostics["raw_generated_text"] = raw_output
    if generator_output.generation_status != "success":
        category, reason = _classify_generator_failure(generator_output)
        failures.append((category, reason))
        diagnostics.update(
            {
                "generation_status": generator_output.generation_status,
                "generation_error_type": generator_output.generation_error_type,
                "generation_error_message": reason,
                "json_extraction_status": "skipped",
                "json_parse_status": "skipped",
                "semantic_correctness_status": SEMANTIC_CORRECTNESS_NOT_EVALUATED,
            }
        )
        return None, failures, diagnostics

    if not raw_output:
        failures.append((FailureCategory.EMPTY_GENERATION_OUTPUT, "empty raw output"))
        diagnostics["json_extraction_status"] = "skipped"
        diagnostics["json_parse_status"] = "skipped"
        diagnostics["semantic_correctness_status"] = SEMANTIC_CORRECTNESS_NOT_EVALUATED
        return None, failures, diagnostics

    parse_result = extract_and_repair_json(raw_output)
    diagnostics["local_repair_operations"] = tuple(parse_result.repair_log)
    diagnostics["extracted_json_text"] = parse_result.extracted_json_text

    if parse_result.parsed_object is None:
        category, reason = _classify_parse_failures(parse_result)
        failures.append((category, reason))
        diagnostics["json_extraction_status"] = (
            "failed" if category == FailureCategory.JSON_EXTRACTION_FAILURE else "partial"
        )
        diagnostics["json_parse_status"] = "failed"
        diagnostics["semantic_correctness_status"] = SEMANTIC_CORRECTNESS_NOT_EVALUATED
        return None, failures, diagnostics

    diagnostics["json_extraction_status"] = "success"
    diagnostics["json_parse_status"] = "success"
    semantic_payload = parse_result.parsed_object

    try:
        validate_semantic_payload(semantic_payload)
        diagnostics["semantic_schema_validation_status"] = "valid"
        diagnostics["semantic_schema_validation_errors"] = ()
    except SemanticPayloadError as exc:
        failures.append((FailureCategory.SEMANTIC_SCHEMA_VALIDATION_FAILURE, str(exc)))
        diagnostics["semantic_schema_validation_status"] = "invalid"
        diagnostics["semantic_schema_validation_errors"] = (str(exc),)
        diagnostics["semantic_correctness_status"] = SEMANTIC_CORRECTNESS_NOT_EVALUATED
        return None, failures, diagnostics

    runtime_metadata = PredictionRuntimeMetadata(
        model_id=envelope.model_repository,
        prompt_hash=prompt_hash,
        generation_seed=request.generation_seed,
        raw_model_output=raw_output,
    )
    try:
        canonical = assemble_prediction_record(
            _prediction_request_context(request),
            semantic_payload,
            runtime_metadata,
            request.provenance_policy,
        )
        diagnostics["canonical_assembly_status"] = "success"
        diagnostics["canonical_assembly_errors"] = ()
    except (PredictionAssemblyError, SemanticPayloadError) as exc:
        failures.append((FailureCategory.CANONICAL_ASSEMBLY_FAILURE, str(exc)))
        diagnostics["canonical_assembly_status"] = "failed"
        diagnostics["canonical_assembly_errors"] = (str(exc),)
        diagnostics["semantic_correctness_status"] = SEMANTIC_CORRECTNESS_NOT_EVALUATED
        return None, failures, diagnostics

    try:
        validate_canonical_record_v2(canonical)
    except Exception as exc:  # noqa: BLE001
        failures.append((FailureCategory.CANONICAL_ASSEMBLY_FAILURE, str(exc)))
        diagnostics["canonical_assembly_status"] = "failed"
        diagnostics["canonical_assembly_errors"] = (str(exc),)
        diagnostics["semantic_correctness_status"] = SEMANTIC_CORRECTNESS_NOT_EVALUATED
        return None, failures, diagnostics

    fixture = integrity_context.to_fixture_dict()
    unsupported_count = count_unsupported_commitments(fixture, canonical)
    unsupported_details: list[str] = []
    if unsupported_count > 0:
        unsupported_details.append(
            f"unsupported_silent_commitments={unsupported_count}"
        )
        failures.append(
            (
                FailureCategory.UNSUPPORTED_SILENT_COMMITMENT,
                f"unsupported commitments: {unsupported_count}",
            )
        )

    diagnostics["unsupported_commitment_count"] = unsupported_count
    diagnostics["unsupported_commitment_details"] = tuple(unsupported_details)
    diagnostics["semantic_correctness_status"] = SEMANTIC_CORRECTNESS_NOT_EVALUATED

    if failures:
        return None, failures, diagnostics

    if canonical.get("id") != request.caller_request_id:
        failures.append(
            (FailureCategory.CANONICAL_ASSEMBLY_FAILURE, "caller request ID not preserved")
        )
        return None, failures, diagnostics
    if canonical.get("command") != request.command:
        failures.append(
            (FailureCategory.CANONICAL_ASSEMBLY_FAILURE, "command not preserved exactly")
        )
        return None, failures, diagnostics

    diagnostics["structural_validity_status"] = "valid"
    diagnostics["semantic_correctness_status"] = SEMANTIC_CORRECTNESS_NOT_EVALUATED
    return canonical, failures, diagnostics


def _is_repairable(failures: list[tuple[FailureCategory, str]]) -> bool:
    if not failures:
        return False
    return all(category in REPAIRABLE_FAILURES for category, _ in failures)


def _make_entry(
    *,
    request: GenerationPipelineRequest,
    attempt_index: int,
    attempt_kind: str,
    envelope: GenerationReadyPromptEnvelope | None,
    structured_metadata: StructuredDecodeMetadata | None,
    backend: BackendIdentity,
    repair_prompt_hash: str | None,
    prompt_message_hash: str | None,
    generator_output: GeneratorOutput | None,
    diagnostics: dict[str, Any],
    failures: list[tuple[FailureCategory, str]],
    disposition: str,
    integrity_context_hash: str | None = None,
) -> AttemptEvidenceEntry:
    categories = tuple(category.value for category, _ in failures)
    reasons = tuple(reason for _, reason in failures)
    return AttemptEvidenceEntry(
        caller_request_id=request.caller_request_id,
        attempt_index=attempt_index,
        attempt_kind=attempt_kind,
        prompt_message_hash=prompt_message_hash,
        rendered_prompt_hash=envelope.rendered_prompt_hash if envelope else None,
        repair_prompt_hash=repair_prompt_hash,
        response_mode_identity=(
            envelope.response_mode_method_identity if envelope else None
        ),
        response_mode_status=envelope.response_mode_status if envelope else None,
        structured_decode_contract_hash=(
            structured_metadata.contract_hash if structured_metadata else None
        ),
        semantic_schema_hash=(
            structured_metadata.schema_hash if structured_metadata else None
        ),
        backend_identifier=backend.backend_identifier,
        backend_configuration_hash=backend.backend_configuration_hash,
        model_repository=envelope.model_repository if envelope else None,
        model_revision=envelope.immutable_model_revision if envelope else None,
        container_sha=request.container_sha,
        raw_generated_text=diagnostics.get("raw_generated_text"),
        generation_status=diagnostics.get("generation_status", generator_output.generation_status if generator_output else None),
        generation_error_type=diagnostics.get("generation_error_type"),
        generation_error_message=diagnostics.get("generation_error_message"),
        engine_request_id=generator_output.engine_request_id if generator_output else None,
        finish_reason=generator_output.finish_reason if generator_output else None,
        prompt_tokens=generator_output.prompt_tokens if generator_output else None,
        completion_tokens=generator_output.completion_tokens if generator_output else None,
        json_extraction_status=diagnostics.get("json_extraction_status"),
        local_repair_operations=diagnostics.get("local_repair_operations", ()),
        extracted_json_text=diagnostics.get("extracted_json_text"),
        json_parse_status=diagnostics.get("json_parse_status"),
        semantic_schema_validation_status=diagnostics.get("semantic_schema_validation_status"),
        semantic_schema_validation_errors=diagnostics.get("semantic_schema_validation_errors", ()),
        canonical_assembly_status=diagnostics.get("canonical_assembly_status"),
        canonical_assembly_errors=diagnostics.get("canonical_assembly_errors", ()),
        unsupported_commitment_count=diagnostics.get("unsupported_commitment_count"),
        unsupported_commitment_details=diagnostics.get("unsupported_commitment_details", ()),
        structural_validity_status=diagnostics.get("structural_validity_status"),
        semantic_correctness_status=diagnostics.get("semantic_correctness_status"),
        integrity_context_hash=integrity_context_hash or diagnostics.get("integrity_context_hash"),
        final_attempt_disposition=disposition,
        failure_categories=categories,
        failure_reasons=reasons,
    )


def run_generation_pipeline(
    request: GenerationPipelineRequest,
    *,
    renderer: GenerationReadyRenderer,
    generator: GenerationAttemptGenerator,
    backend: BackendIdentity,
    structured_decode_readiness: StructuredDecodeReadiness | None,
    policy: GenerationPolicy | None = None,
    structured_decode_contract: StructuredDecodeContract | None = None,
    pipeline_contract: dict[str, object] | None = None,
) -> GenerationPipelineResult:
    ledger = AttemptEvidenceLedger()
    caller_command_hash = sha256_hex(request.command.encode("utf-8"))
    schema_hash = model_semantic_output_schema_hash()

    input_errors = validate_pipeline_request(request)
    if input_errors:
        return GenerationPipelineResult(
            request_id=request.caller_request_id,
            final_status=PipelineFinalStatus.REJECTED_NON_RETRYABLE.value,
            accepted_canonical_prediction=None,
            attempt_entries=tuple(ledger.entries),
            attempts_used=0,
            attempts_exhausted=False,
            failure_categories=(FailureCategory.INVALID_CALLER_INPUT.value,),
            failure_reasons=tuple(input_errors),
            semantic_schema_hash=schema_hash,
            structured_decode_contract_hash="",
            caller_command_hash=caller_command_hash,
            integrity_context_hash="",
            accepted_raw_attempt_index=None,
        )

    try:
        active_policy = policy or load_generation_policy()
        decode_contract = structured_decode_contract or load_structured_decode_contract()
        _ = pipeline_contract or load_pipeline_contract()
        integrity_context = _coerce_integrity_context(request.integrity_context)
        integrity_hash = integrity_context.hash()
    except Exception as exc:  # noqa: BLE001
        return GenerationPipelineResult(
            request_id=request.caller_request_id,
            final_status=PipelineFinalStatus.REJECTED_NON_RETRYABLE.value,
            accepted_canonical_prediction=None,
            attempt_entries=tuple(ledger.entries),
            attempts_used=0,
            attempts_exhausted=False,
            failure_categories=(FailureCategory.POLICY_CONFIGURATION_CORRUPTION.value,),
            failure_reasons=(_sanitize_error_message(str(exc)),),
            semantic_schema_hash=schema_hash,
            structured_decode_contract_hash="",
            caller_command_hash=caller_command_hash,
            integrity_context_hash="",
            accepted_raw_attempt_index=None,
        )

    contract_hash = structured_decode_contract_hash(decode_contract)
    prompt_request = _prompt_build_request(request)
    system_message = build_system_message()
    prior_failures: tuple[str, ...] = ()
    prior_raw_output: str | None = None
    repair_prompt_hash: str | None = None
    generator_calls = 0

    for attempt_index in range(active_policy.total_model_attempts):
        attempt_kind = ATTEMPT_KINDS[attempt_index]
        current_repair_hash: str | None = None

        if attempt_index == 0:
            messages = build_prompt_messages(prompt_request)
            prompt_hash = compute_prompt_hash(prompt_request)
        else:
            repair = build_repair_prompt(
                RepairPromptRequest(
                    original_request=prompt_request,
                    attempt_number=attempt_index,
                    validation_failures=prior_failures,
                    prior_raw_output=prior_raw_output,
                )
            )
            current_repair_hash = repair.repair_prompt_hash
            repair_prompt_hash = repair.repair_prompt_hash
            messages = build_repair_messages(system_message, prompt_request, repair)
            prompt_hash = _compute_message_hash(messages)

        prompt_message_hash = _compute_message_hash(messages)
        envelope = renderer.render(messages)
        envelope_failures = verify_generation_ready_envelope(envelope)
        readiness_failures = verify_structured_decode_readiness(
            structured_decode_readiness, decode_contract
        )
        pre_gen_failures = envelope_failures + readiness_failures

        if pre_gen_failures:
            entry = _make_entry(
                request=request,
                attempt_index=attempt_index,
                attempt_kind=attempt_kind,
                envelope=envelope,
                structured_metadata=(
                    structured_decode_readiness.metadata
                    if structured_decode_readiness
                    else None
                ),
                backend=backend,
                repair_prompt_hash=current_repair_hash,
                prompt_message_hash=prompt_message_hash,
                generator_output=None,
                diagnostics={
                    "generation_status": "skipped",
                    "json_extraction_status": "skipped",
                    "json_parse_status": "skipped",
                },
                failures=pre_gen_failures,
                disposition=AttemptDisposition.NON_RETRYABLE_REJECTED.value,
                integrity_context_hash=integrity_hash,
            )
            ledger.append(entry)
            categories = tuple(category.value for category, _ in pre_gen_failures)
            reasons = tuple(reason for _, reason in pre_gen_failures)
            return GenerationPipelineResult(
                request_id=request.caller_request_id,
                final_status=PipelineFinalStatus.REJECTED_NON_RETRYABLE.value,
                accepted_canonical_prediction=None,
                attempt_entries=tuple(ledger.entries),
                attempts_used=generator_calls,
                attempts_exhausted=False,
                failure_categories=categories,
                failure_reasons=reasons,
                semantic_schema_hash=schema_hash,
                structured_decode_contract_hash=contract_hash,
                caller_command_hash=caller_command_hash,
                integrity_context_hash=integrity_hash,
                accepted_raw_attempt_index=None,
            )

        try:
            generator_output = generator.generate(
                rendered_prompt=envelope.rendered_prompt_text,
                attempt_index=attempt_index,
                caller_request_id=request.caller_request_id,
            )
        except Exception as exc:  # noqa: BLE001 - unknown generator exceptions are non-retryable
            generator_calls += 1
            generator_output = GeneratorOutput(
                raw_output="",
                generation_status="error",
                generation_error_type=FailureCategory.UNKNOWN_EXCEPTION.value,
                generation_error_message=_sanitize_error_message(
                    f"{type(exc).__name__}: {exc}"
                ),
            )
        else:
            generator_calls += 1
        defensive_copy_metadata(generator_output.runtime_metadata)

        canonical, failures, diagnostics = _process_attempt_output(
            request=request,
            integrity_context=integrity_context,
            generator_output=generator_output,
            envelope=envelope,
            prompt_hash=prompt_hash,
        )
        diagnostics["generation_status"] = generator_output.generation_status

        if canonical is not None and not failures:
            entry = _make_entry(
                request=request,
                attempt_index=attempt_index,
                attempt_kind=attempt_kind,
                envelope=envelope,
                structured_metadata=structured_decode_readiness.metadata,
                backend=backend,
                repair_prompt_hash=current_repair_hash,
                prompt_message_hash=prompt_message_hash,
                generator_output=generator_output,
                diagnostics=diagnostics,
                failures=[],
                disposition=AttemptDisposition.ACCEPTED.value,
                integrity_context_hash=integrity_hash,
            )
            ledger.append(entry)
            return GenerationPipelineResult(
                request_id=request.caller_request_id,
                final_status=PipelineFinalStatus.ACCEPTED.value,
                accepted_canonical_prediction=canonical,
                attempt_entries=tuple(ledger.entries),
                attempts_used=generator_calls,
                attempts_exhausted=False,
                failure_categories=(),
                failure_reasons=(),
                semantic_schema_hash=schema_hash,
                structured_decode_contract_hash=contract_hash,
                caller_command_hash=caller_command_hash,
                integrity_context_hash=integrity_hash,
                accepted_raw_attempt_index=attempt_index,
            )

        disposition = (
            AttemptDisposition.REPAIRABLE_REJECTED.value
            if _is_repairable(failures)
            else AttemptDisposition.NON_RETRYABLE_REJECTED.value
        )
        entry = _make_entry(
            request=request,
            attempt_index=attempt_index,
            attempt_kind=attempt_kind,
            envelope=envelope,
            structured_metadata=structured_decode_readiness.metadata,
            backend=backend,
            repair_prompt_hash=current_repair_hash,
            prompt_message_hash=prompt_message_hash,
            generator_output=generator_output,
            diagnostics=diagnostics,
            failures=failures,
            disposition=disposition,
            integrity_context_hash=integrity_hash,
        )
        ledger.append(entry)

        if not _is_repairable(failures):
            categories = tuple(category.value for category, _ in failures)
            reasons = tuple(reason for _, reason in failures)
            return GenerationPipelineResult(
                request_id=request.caller_request_id,
                final_status=PipelineFinalStatus.REJECTED_NON_RETRYABLE.value,
                accepted_canonical_prediction=None,
                attempt_entries=tuple(ledger.entries),
                attempts_used=generator_calls,
                attempts_exhausted=False,
                failure_categories=categories,
                failure_reasons=reasons,
                semantic_schema_hash=schema_hash,
                structured_decode_contract_hash=contract_hash,
                caller_command_hash=caller_command_hash,
                integrity_context_hash=integrity_hash,
                accepted_raw_attempt_index=None,
            )

        prior_failures = tuple(reason for _, reason in failures)
        prior_raw_output = generator_output.raw_output

        if attempt_index >= active_policy.total_model_attempts - 1:
            break

    all_categories: list[str] = []
    all_reasons: list[str] = []
    for entry in ledger.entries:
        all_categories.extend(entry.failure_categories)
        all_reasons.extend(entry.failure_reasons)

    return GenerationPipelineResult(
        request_id=request.caller_request_id,
        final_status=PipelineFinalStatus.REJECTED_AFTER_ATTEMPTS.value,
        accepted_canonical_prediction=None,
        attempt_entries=tuple(ledger.entries),
        attempts_used=generator_calls,
        attempts_exhausted=True,
        failure_categories=tuple(all_categories),
        failure_reasons=tuple(all_reasons),
        semantic_schema_hash=schema_hash,
        structured_decode_contract_hash=contract_hash,
        caller_command_hash=caller_command_hash,
        integrity_context_hash=integrity_hash,
        accepted_raw_attempt_index=None,
    )
