"""ModelClient protocol, runtime binding, and request/result types."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from ambiguity_manager.model.errors import ModelClientError

VALID_MESSAGE_ROLES = frozenset({"system", "user", "assistant"})


def validate_messages(messages: list[dict[str, str]]) -> None:
    if not messages:
        raise ModelClientError("messages must not be empty")
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise ModelClientError(f"messages[{index}] must be an object")
        role = message.get("role")
        content = message.get("content")
        if role not in VALID_MESSAGE_ROLES:
            raise ModelClientError(f"messages[{index}].role is invalid")
        if not isinstance(content, str) or not content.strip():
            raise ModelClientError(f"messages[{index}].content must be a non-empty string")


@dataclass(frozen=True)
class ModelRuntimeSpec:
    backend: str
    model_id: str
    immutable_revision: str
    tokenizer_revision: str
    quantisation: str
    environment_id: str
    device_policy: str


@dataclass(frozen=True)
class GenerateJsonRequest:
    messages: list[dict[str, str]]
    json_schema: dict[str, Any]
    seed: int | None = None
    temperature: float = 0.1
    top_p: float = 1.0
    requested_max_new_tokens: int = 2048
    timeout_s: float = 300.0
    fixture_id: str | None = None
    run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_messages(self.messages)
        if self.requested_max_new_tokens <= 0:
            raise ModelClientError("requested_max_new_tokens must be positive")
        if self.timeout_s <= 0:
            raise ModelClientError("timeout_s must be positive")


@dataclass
class GenerateJsonResult:
    request_id: str
    backend: str
    model_id: str
    immutable_revision: str
    tokenizer_revision: str
    quantisation: str
    environment_id: str
    device_policy: str
    raw_output: str
    extracted_json_text: str | None
    parsed_object: dict[str, Any] | None
    schema_valid: bool
    schema_errors: list[str]
    repair_attempts: int
    repair_log: list[str]
    final_status: str
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    peak_vram_mib: float | None = None
    runtime_metadata: dict[str, Any] = field(default_factory=dict)
    hardware_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_runtime(
        cls,
        *,
        runtime: ModelRuntimeSpec,
        request_id: str,
        raw_output: str,
        extracted_json_text: str | None,
        parsed_object: dict[str, Any] | None,
        schema_valid: bool,
        schema_errors: list[str],
        repair_attempts: int,
        repair_log: list[str],
        final_status: str,
        latency_ms: float,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        peak_vram_mib: float | None = None,
        runtime_metadata: dict[str, Any] | None = None,
        hardware_metadata: dict[str, Any] | None = None,
    ) -> "GenerateJsonResult":
        return cls(
            request_id=request_id,
            backend=runtime.backend,
            model_id=runtime.model_id,
            immutable_revision=runtime.immutable_revision,
            tokenizer_revision=runtime.tokenizer_revision,
            quantisation=runtime.quantisation,
            environment_id=runtime.environment_id,
            device_policy=runtime.device_policy,
            raw_output=raw_output,
            extracted_json_text=extracted_json_text,
            parsed_object=parsed_object,
            schema_valid=schema_valid,
            schema_errors=schema_errors,
            repair_attempts=repair_attempts,
            repair_log=repair_log,
            final_status=final_status,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=completion_tokens if completion_tokens is not None else None,
            peak_vram_mib=peak_vram_mib,
            runtime_metadata=dict(runtime_metadata or {}),
            hardware_metadata=dict(hardware_metadata or {}),
        )


class ModelClient(Protocol):
    @property
    def runtime(self) -> ModelRuntimeSpec:
        ...

    def generate_json(self, request: GenerateJsonRequest) -> GenerateJsonResult:
        ...


def monotonic_ms() -> float:
    return time.perf_counter() * 1000.0
