"""vLLM batch backend adapter for the T12 D1C1 generation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ambiguity_manager.model.generation_pipeline import GeneratorOutput

REPAIRABLE_ERROR_TYPES = frozenset({"transient_output_production_failure"})
NON_RETRYABLE_ERROR_TYPES = frozenset(
    {
        "backend_dependency_failure",
        "backend_configuration_failure",
        "backend_startup_failure",
        "engine_failure",
        "malformed_engine_output",
        "multiple_completions",
        "missing_engine_output",
        "excess_engine_output",
        "engine_output_order_mismatch",
        "unknown_output_id",
        "backend_not_started",
    }
)


@dataclass
class VllmPipelineGenerator:
    """Single persistent backend wrapper implementing GenerationAttemptGenerator."""

    backend: Any
    ordinal_base: int = 0
    generate_calls: list[dict[str, Any]] = field(default_factory=list)

    def generate(
        self,
        *,
        rendered_prompt: str,
        attempt_index: int,
        caller_request_id: str,
    ) -> GeneratorOutput:
        from ambiguity_manager.model.backends.vllm_batch import (
            BatchRequest,
            VllmBatchBackendError,
        )

        self.generate_calls.append(
            {
                "rendered_prompt": rendered_prompt,
                "attempt_index": attempt_index,
                "caller_request_id": caller_request_id,
            }
        )
        ordinal = self.ordinal_base + attempt_index
        batch_request = BatchRequest(
            request_id=caller_request_id,
            prompt=rendered_prompt,
            ordinal=ordinal,
            synthetic=True,
            metadata={"attempt_index": attempt_index},
        )
        try:
            results = self.backend.generate_batch([batch_request])
        except VllmBatchBackendError as exc:
            return GeneratorOutput(
                raw_output="",
                generation_status="error",
                generation_error_type=_classify_backend_error(str(exc)),
                generation_error_message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            return GeneratorOutput(
                raw_output="",
                generation_status="error",
                generation_error_type="unknown_exception",
                generation_error_message=f"{type(exc).__name__}: {exc}",
            )

        if not results:
            return GeneratorOutput(
                raw_output="",
                generation_status="error",
                generation_error_type="engine_failure",
                generation_error_message="backend returned no results",
            )

        result = results[0]
        if result.generation_status == "success":
            return GeneratorOutput(
                raw_output=result.raw_text,
                generation_status="success",
                engine_request_id=(
                    str(result.engine_request_id) if result.engine_request_id is not None else None
                ),
                finish_reason=result.finish_reason,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                runtime_metadata={
                    "backend_identifier": result.backend_identifier,
                    "config_hash": result.config_hash,
                },
            )

        error_type = result.error_type or "unclassified_generator_error"
        mapped_type = _map_failure_error_type(error_type)
        return GeneratorOutput(
            raw_output=result.raw_text or "",
            generation_status="error",
            generation_error_type=mapped_type,
            generation_error_message=result.error_message or error_type,
            engine_request_id=(
                str(result.engine_request_id) if result.engine_request_id is not None else None
            ),
            finish_reason=result.finish_reason,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            runtime_metadata={
                "backend_identifier": result.backend_identifier,
                "config_hash": result.config_hash,
            },
        )


def _classify_backend_error(message: str) -> str:
    lowered = message.lower()
    if "not installed" in lowered or "unavailable" in lowered:
        return "backend_dependency_failure"
    if "runtime_config" in lowered or "validation" in lowered:
        return "backend_configuration_failure"
    if "startup" in lowered or "engine_startup" in lowered:
        return "backend_startup_failure"
    if "structured_decode" in lowered:
        return "structured_decode_failure"
    return "engine_failure"


def _map_failure_error_type(error_type: str) -> str:
    if error_type in REPAIRABLE_ERROR_TYPES:
        return error_type
    if error_type in NON_RETRYABLE_ERROR_TYPES:
        return error_type
    if error_type == "transient_output_production_failure":
        return error_type
    return "unclassified_generator_error"
