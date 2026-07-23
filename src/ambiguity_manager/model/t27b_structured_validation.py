"""Multi-stage structured-output validation for T27B reporting.

Retains T27 ``validate_structured_model_output`` unchanged for regression.
Does not weaken ``validate_semantic_payload``. Constrained syntax alone is
not acceptance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ambiguity_manager.model.integrity import count_unsupported_commitments
from ambiguity_manager.model.parser import extract_and_repair_json
from ambiguity_manager.model.prediction_contract import (
    MODEL_OUTPUT_REQUIRED_FIELDS,
    SemanticPayloadError,
    validate_semantic_payload,
)
from ambiguity_manager.model.structured_output_validation import (
    STATUS_ACCEPTED,
    STATUS_JSON_PARSE_FAILED,
    STATUS_NO_JSON,
    STATUS_SAFETY_REJECTED,
    isolate_generated_continuation,
    validate_structured_model_output,
)
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES

FAILURE_STAGES = frozenset(
    {
        "no_json",
        "json_parse_failed",
        "wrong_top_level_type",
        "missing_required_field",
        "unknown_field",
        "wrong_enum",
        "wrong_nested_type",
        "invalid_CPC_shape",
        "invalid_candidate_shape",
        "invalid_evidence_shape",
        "semantic_contract_failure",
        "safety_rejection",
        "truncation",
        "prompt_echo",
        "other",
    }
)


class T27BStructuredValidationError(RuntimeError):
    """Raised for contract-level misuse of the T27B validator."""


@dataclass(frozen=True)
class T27BStructuredVerdict:
    transport_status: str
    json_parse_status: str
    schema_status: str
    semantic_status: str
    safety_status: str
    final_acceptance_status: str
    failure_stage: str | None
    raw_output: str
    generated_continuation: str
    parsed_output: dict[str, Any] | None
    failure_field_paths: tuple[str, ...]
    schema_error: str | None
    safety_findings: tuple[str, ...]
    legacy_status: str

    @property
    def accepted(self) -> bool:
        return self.final_acceptance_status == "accepted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "transport_status": self.transport_status,
            "json_parse_status": self.json_parse_status,
            "schema_status": self.schema_status,
            "semantic_status": self.semantic_status,
            "safety_status": self.safety_status,
            "final_acceptance_status": self.final_acceptance_status,
            "failure_stage": self.failure_stage,
            "raw_output": self.raw_output,
            "generated_continuation": self.generated_continuation,
            "parsed_output": self.parsed_output,
            "failure_field_paths": list(self.failure_field_paths),
            "schema_error": self.schema_error,
            "safety_findings": list(self.safety_findings),
            "legacy_status": self.legacy_status,
            "accepted": self.accepted,
        }


def _classify_schema_error(message: str, parsed: Mapping[str, Any] | None) -> tuple[str, list[str]]:
    lower = message.lower()
    paths: list[str] = []
    if "unknown model fields" in lower:
        return "unknown_field", paths
    if "missing required semantic fields" in lower:
        return "missing_required_field", paths
    if "runner-owned" in lower or "label_eligibility" in lower:
        return "unknown_field", paths
    if "enum" in lower or "must be one of" in lower:
        return "wrong_enum", paths
    if "cpc" in lower:
        return "invalid_CPC_shape", paths
    if "candidate" in lower:
        return "invalid_candidate_shape", paths
    if "evidence" in lower:
        return "invalid_evidence_shape", paths
    if "type" in lower or "not of type" in lower:
        return "wrong_nested_type", paths
    if parsed is not None:
        missing = sorted(MODEL_OUTPUT_REQUIRED_FIELDS - set(parsed))
        unknown = sorted(set(parsed) - MODEL_OUTPUT_REQUIRED_FIELDS)
        if unknown:
            return "unknown_field", unknown
        if missing:
            return "missing_required_field", missing
        cpc = parsed.get("cpc")
        if not isinstance(cpc, dict) or set(cpc.keys()) != set(CPC_SLOT_NAMES):
            return "invalid_CPC_shape", ["cpc"]
    return "semantic_contract_failure", paths


def validate_t27b_structured_model_output(
    *,
    prompt: str,
    raw_output: str,
    support_fixture: Mapping[str, Any] | None = None,
) -> T27BStructuredVerdict:
    """Multi-stage T27B validator; still uses validate_semantic_payload strictly."""
    if not isinstance(raw_output, str):
        raise T27BStructuredValidationError("raw_output_must_be_str")

    legacy = validate_structured_model_output(
        prompt=prompt,
        raw_output=raw_output,
        support_fixture=support_fixture,
    )

    continuation = isolate_generated_continuation(prompt=prompt, raw_output=raw_output)
    transport_status = "ok"
    if raw_output.startswith(prompt) and raw_output.strip() == prompt.strip():
        transport_status = "prompt_echo_only"

    json_parse_status = "not_attempted"
    schema_status = "not_attempted"
    semantic_status = "not_attempted"
    safety_status = "not_attempted"
    failure_stage: str | None = None
    failure_paths: list[str] = []
    parsed: dict[str, Any] | None = None
    schema_error: str | None = None
    safety_findings: list[str] = []

    stripped = continuation.strip()
    if not stripped:
        return T27BStructuredVerdict(
            transport_status=transport_status,
            json_parse_status="no_json",
            schema_status="not_reached",
            semantic_status="not_reached",
            safety_status="not_reached",
            final_acceptance_status="rejected",
            failure_stage="no_json",
            raw_output=raw_output,
            generated_continuation=continuation,
            parsed_output=None,
            failure_field_paths=tuple(),
            schema_error="empty_continuation",
            safety_findings=tuple(),
            legacy_status=legacy.status,
        )

    if transport_status == "prompt_echo_only":
        failure_stage = "prompt_echo"

    parse = extract_and_repair_json(continuation)
    if parse.parsed_object is None:
        braces = "{" in continuation and "}" in continuation
        json_parse_status = STATUS_JSON_PARSE_FAILED if braces else STATUS_NO_JSON
        failure_stage = failure_stage or ("json_parse_failed" if braces else "no_json")
        if continuation.rstrip().endswith(",") or continuation.count("{") > continuation.count("}"):
            failure_stage = "truncation"
        return T27BStructuredVerdict(
            transport_status=transport_status,
            json_parse_status=json_parse_status,
            schema_status="not_reached",
            semantic_status="not_reached",
            safety_status="not_reached",
            final_acceptance_status="rejected",
            failure_stage=failure_stage,
            raw_output=raw_output,
            generated_continuation=continuation,
            parsed_output=None,
            failure_field_paths=tuple(),
            schema_error="json_parse_failed",
            safety_findings=tuple(),
            legacy_status=legacy.status,
        )

    if not isinstance(parse.parsed_object, dict):
        return T27BStructuredVerdict(
            transport_status=transport_status,
            json_parse_status="parsed",
            schema_status="invalid",
            semantic_status="not_reached",
            safety_status="not_reached",
            final_acceptance_status="rejected",
            failure_stage="wrong_top_level_type",
            raw_output=raw_output,
            generated_continuation=continuation,
            parsed_output=None,
            failure_field_paths=tuple(),
            schema_error="wrong_top_level_type",
            safety_findings=tuple(),
            legacy_status=legacy.status,
        )

    json_parse_status = "parsed"
    parsed = dict(parse.parsed_object)

    unknown = sorted(set(parsed) - MODEL_OUTPUT_REQUIRED_FIELDS)
    missing = sorted(MODEL_OUTPUT_REQUIRED_FIELDS - set(parsed))
    if unknown:
        return T27BStructuredVerdict(
            transport_status=transport_status,
            json_parse_status=json_parse_status,
            schema_status="invalid",
            semantic_status="not_reached",
            safety_status="not_reached",
            final_acceptance_status="rejected",
            failure_stage="unknown_field",
            raw_output=raw_output,
            generated_continuation=continuation,
            parsed_output=parsed,
            failure_field_paths=tuple(unknown),
            schema_error=f"unknown model fields: {unknown}",
            safety_findings=tuple(),
            legacy_status=legacy.status,
        )
    if missing:
        return T27BStructuredVerdict(
            transport_status=transport_status,
            json_parse_status=json_parse_status,
            schema_status="invalid",
            semantic_status="not_reached",
            safety_status="not_reached",
            final_acceptance_status="rejected",
            failure_stage="missing_required_field",
            raw_output=raw_output,
            generated_continuation=continuation,
            parsed_output=parsed,
            failure_field_paths=tuple(missing),
            schema_error=f"missing required semantic fields: {missing}",
            safety_findings=tuple(),
            legacy_status=legacy.status,
        )

    try:
        validate_semantic_payload(parsed)
    except SemanticPayloadError as exc:
        stage, paths = _classify_schema_error(str(exc), parsed)
        return T27BStructuredVerdict(
            transport_status=transport_status,
            json_parse_status=json_parse_status,
            schema_status="invalid",
            semantic_status="invalid",
            safety_status="not_reached",
            final_acceptance_status="rejected",
            failure_stage=stage,
            raw_output=raw_output,
            generated_continuation=continuation,
            parsed_output=parsed,
            failure_field_paths=tuple(paths),
            schema_error=str(exc),
            safety_findings=tuple(),
            legacy_status=legacy.status,
        )

    schema_status = "valid"
    semantic_status = "valid"

    fixture = dict(support_fixture or {})
    unsupported = count_unsupported_commitments(fixture, parsed)
    if unsupported > 0:
        return T27BStructuredVerdict(
            transport_status=transport_status,
            json_parse_status=json_parse_status,
            schema_status=schema_status,
            semantic_status=semantic_status,
            safety_status="rejected",
            final_acceptance_status="rejected",
            failure_stage="safety_rejection",
            raw_output=raw_output,
            generated_continuation=continuation,
            parsed_output=parsed,
            failure_field_paths=tuple(),
            schema_error=None,
            safety_findings=(f"unsupported_silent_commitments={unsupported}",),
            legacy_status=legacy.status,
        )

    return T27BStructuredVerdict(
        transport_status=transport_status,
        json_parse_status=json_parse_status,
        schema_status=schema_status,
        semantic_status=semantic_status,
        safety_status="accepted",
        final_acceptance_status="accepted",
        failure_stage=None,
        raw_output=raw_output,
        generated_continuation=continuation,
        parsed_output=parsed,
        failure_field_paths=tuple(),
        schema_error=None,
        safety_findings=tuple(),
        legacy_status=legacy.status,
    )
