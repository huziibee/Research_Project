"""Real local Hugging Face transformers backend with process-boundary generation."""

from __future__ import annotations

import uuid
from typing import Any

from ambiguity_manager.governance.model_licence import MANDATORY_CONTEXT_LIMIT
from ambiguity_manager.model.checkpoint_load import BACKEND_ID, DEFAULT_TIMEOUT_S
from ambiguity_manager.model.errors import ModelBackendUnavailableError, ModelClientError
from ambiguity_manager.model.hf_load_helpers import generation_worker
from ambiguity_manager.model.parser import extract_and_repair_json
from ambiguity_manager.model.protocol import (
    GenerateJsonRequest,
    GenerateJsonResult,
    ModelRuntimeSpec,
    monotonic_ms,
)
from ambiguity_manager.model.worker_process import WorkerResult, run_worker_with_timeout
from ambiguity_manager.schema.v2.validation import validate_canonical_record_v2


class HfTransformersBackend:
    def __init__(self, runtime: ModelRuntimeSpec) -> None:
        from ambiguity_manager.model.checkpoint_load import validate_runtime_immutable

        if runtime.backend != BACKEND_ID:
            raise ModelClientError(f"backend must be {BACKEND_ID}")
        validate_runtime_immutable(runtime)
        self._runtime = runtime

    @property
    def runtime(self) -> ModelRuntimeSpec:
        return self._runtime

    def generate_json(self, request: GenerateJsonRequest) -> GenerateJsonResult:
        start = monotonic_ms()
        request_id = request.run_id or str(uuid.uuid4())

        do_sample = request.temperature > 0.0
        payload = {
            "runtime": {
                "backend": self._runtime.backend,
                "model_id": self._runtime.model_id,
                "immutable_revision": self._runtime.immutable_revision,
                "tokenizer_revision": self._runtime.tokenizer_revision,
                "quantisation": self._runtime.quantisation,
                "environment_id": self._runtime.environment_id,
                "device_policy": self._runtime.device_policy,
            },
            "request": {
                "messages": request.messages,
                "seed": request.seed if request.seed is not None else 0,
                "do_sample": do_sample,
                "top_p": request.top_p if do_sample else None,
                "requested_max_new_tokens": request.requested_max_new_tokens,
            },
            "model_context_limit": MANDATORY_CONTEXT_LIMIT,
        }

        worker_result = run_worker_with_timeout(
            generation_worker,
            args=(payload,),
            timeout_s=request.timeout_s,
        )

        if worker_result.status == "timeout":
            return GenerateJsonResult.from_runtime(
                runtime=self._runtime,
                request_id=request_id,
                raw_output="",
                extracted_json_text=None,
                parsed_object=None,
                schema_valid=False,
                schema_errors=["generation timed out"],
                repair_attempts=0,
                repair_log=[],
                final_status="timeout",
                latency_ms=monotonic_ms() - start,
                runtime_metadata={"worker_status": "timeout", "timeout_s": request.timeout_s},
            )

        if worker_result.status != "success" or worker_result.payload is None:
            error = worker_result.error or "worker failed"
            return GenerateJsonResult.from_runtime(
                runtime=self._runtime,
                request_id=request_id,
                raw_output="",
                extracted_json_text=None,
                parsed_object=None,
                schema_valid=False,
                schema_errors=[error],
                repair_attempts=0,
                repair_log=[],
                final_status="backend_error",
                latency_ms=monotonic_ms() - start,
                runtime_metadata={"worker_status": worker_result.status, "error": error},
            )

        return self._result_from_worker_payload(
            request_id=request_id,
            worker_payload=worker_result.payload,
            worker_result=worker_result,
            latency_ms=monotonic_ms() - start,
        )

    def _result_from_worker_payload(
        self,
        *,
        request_id: str,
        worker_payload: dict[str, Any],
        worker_result: WorkerResult,
        latency_ms: float,
    ) -> GenerateJsonResult:
        raw_output = str(worker_payload.get("raw_output", ""))
        parse_result = extract_and_repair_json(raw_output)
        schema_valid = False
        schema_errors: list[str] = []
        if parse_result.parsed_object is not None:
            try:
                validate_canonical_record_v2(parse_result.parsed_object)
                schema_valid = True
            except Exception as exc:  # noqa: BLE001
                schema_errors = [str(exc)]

        final_status = "success" if schema_valid else "schema_invalid"
        if parse_result.parsed_object is None:
            final_status = "parse_failed"
        if not raw_output.strip():
            final_status = "empty_output"

        return GenerateJsonResult.from_runtime(
            runtime=self._runtime,
            request_id=request_id,
            raw_output=parse_result.raw_output,
            extracted_json_text=parse_result.extracted_json_text,
            parsed_object=parse_result.parsed_object,
            schema_valid=schema_valid,
            schema_errors=schema_errors,
            repair_attempts=parse_result.repair_attempts,
            repair_log=parse_result.repair_log,
            final_status=final_status,
            latency_ms=latency_ms,
            prompt_tokens=worker_payload.get("prompt_tokens"),
            completion_tokens=worker_payload.get("completion_tokens"),
            peak_vram_mib=worker_payload.get("peak_vram_mib"),
            runtime_metadata={
                "backend_impl": BACKEND_ID,
                "effective_max_new_tokens": worker_payload.get("effective_max_new_tokens"),
                "quantisation": worker_payload.get("quantisation"),
                "worker_process_exit_completed": worker_result.worker_process_exit_completed,
                "worker_exit_code": worker_result.worker_exit_code,
            },
        )


def create_hf_backend(runtime: ModelRuntimeSpec) -> HfTransformersBackend:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError as exc:
        raise ModelBackendUnavailableError(
            "hf_transformers_local backend requires optional ML dependencies"
        ) from exc

    return HfTransformersBackend(runtime)
