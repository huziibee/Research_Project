"""Strict structured-output validation for task-aligned QLoRA smoke (T27).

Removes the weak “contains braces” acceptance path. A result passes only when
the generated continuation is isolated from the prompt, parses as JSON, passes
the strict model-facing semantic schema, and passes safety/unsupported-
commitment checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ambiguity_manager.model.integrity import count_unsupported_commitments
from ambiguity_manager.model.parser import extract_and_repair_json
from ambiguity_manager.model.prediction_contract import (
    SemanticPayloadError,
    validate_semantic_payload,
)

STATUS_NO_JSON = "no_json"
STATUS_JSON_PARSE_FAILED = "json_parse_failed"
STATUS_SCHEMA_INVALID = "schema_invalid"
STATUS_SAFETY_REJECTED = "safety_rejected"
STATUS_ACCEPTED = "accepted"

STRICT_STATUSES = frozenset(
    {
        STATUS_NO_JSON,
        STATUS_JSON_PARSE_FAILED,
        STATUS_SCHEMA_INVALID,
        STATUS_SAFETY_REJECTED,
        STATUS_ACCEPTED,
    }
)


class StructuredOutputValidationError(RuntimeError):
    """Raised for contract-level misuse of the validator."""


@dataclass(frozen=True)
class StructuredOutputVerdict:
    status: str
    raw_output: str
    generated_continuation: str
    parsed_output: dict[str, Any] | None
    schema_error: str | None
    safety_findings: list[str]
    braces_only_rejected: bool

    @property
    def accepted(self) -> bool:
        return self.status == STATUS_ACCEPTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "raw_output": self.raw_output,
            "generated_continuation": self.generated_continuation,
            "parsed_output": self.parsed_output,
            "schema_error": self.schema_error,
            "safety_findings": list(self.safety_findings),
            "braces_only_rejected": self.braces_only_rejected,
            "accepted": self.accepted,
        }


def isolate_generated_continuation(*, prompt: str, raw_output: str) -> str:
    """Exclude prompt echo from the generated continuation when present."""
    if raw_output.startswith(prompt):
        return raw_output[len(prompt) :].lstrip()
    # Some generators decode the full sequence including prompt.
    marker = "[OUTPUT_SCHEMA_INSTRUCTIONS]"
    if marker in raw_output and marker in prompt:
        # Prefer the text after the last user content if the prompt was echoed.
        idx = raw_output.find(prompt)
        if idx == 0:
            return raw_output[len(prompt) :].lstrip()
    return raw_output


def validate_structured_model_output(
    *,
    prompt: str,
    raw_output: str,
    support_fixture: Mapping[str, Any] | None = None,
) -> StructuredOutputVerdict:
    """Strict structured-output gate (no braces-only acceptance)."""
    if not isinstance(raw_output, str):
        raise StructuredOutputValidationError("raw_output_must_be_str")

    continuation = isolate_generated_continuation(prompt=prompt, raw_output=raw_output)
    braces_only = ("{" in continuation and "}" in continuation)

    # Reject coherent prose / braces-only without requiring parse success.
    stripped = continuation.strip()
    if not stripped:
        return StructuredOutputVerdict(
            status=STATUS_NO_JSON,
            raw_output=raw_output,
            generated_continuation=continuation,
            parsed_output=None,
            schema_error="empty_continuation",
            safety_findings=[],
            braces_only_rejected=False,
        )

    parse = extract_and_repair_json(continuation)
    if parse.parsed_object is None:
        # Braces present but not valid JSON still fail.
        status = STATUS_JSON_PARSE_FAILED if braces_only else STATUS_NO_JSON
        return StructuredOutputVerdict(
            status=status,
            raw_output=raw_output,
            generated_continuation=continuation,
            parsed_output=None,
            schema_error="json_parse_failed",
            safety_findings=[],
            braces_only_rejected=braces_only and status != STATUS_ACCEPTED,
        )

    try:
        validate_semantic_payload(parse.parsed_object)
    except SemanticPayloadError as exc:
        return StructuredOutputVerdict(
            status=STATUS_SCHEMA_INVALID,
            raw_output=raw_output,
            generated_continuation=continuation,
            parsed_output=dict(parse.parsed_object),
            schema_error=str(exc),
            safety_findings=[],
            braces_only_rejected=False,
        )

    safety_findings: list[str] = []
    fixture = dict(support_fixture or {})
    unsupported = count_unsupported_commitments(fixture, parse.parsed_object)
    if unsupported > 0:
        safety_findings.append(f"unsupported_silent_commitments={unsupported}")
        return StructuredOutputVerdict(
            status=STATUS_SAFETY_REJECTED,
            raw_output=raw_output,
            generated_continuation=continuation,
            parsed_output=dict(parse.parsed_object),
            schema_error=None,
            safety_findings=safety_findings,
            braces_only_rejected=False,
        )

    return StructuredOutputVerdict(
        status=STATUS_ACCEPTED,
        raw_output=raw_output,
        generated_continuation=continuation,
        parsed_output=dict(parse.parsed_object),
        schema_error=None,
        safety_findings=[],
        braces_only_rejected=False,
    )


def braces_only_must_fail(text: str) -> StructuredOutputVerdict:
    """Helper used by tests: text containing only braces-like noise must not pass."""
    return validate_structured_model_output(prompt="PROMPT", raw_output=text)
