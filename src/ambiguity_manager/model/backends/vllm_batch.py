"""Persistent direct-Python vLLM batch backend for T12 cluster execution."""

from __future__ import annotations

import importlib
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.cluster._config_loader import load_json_config
from ambiguity_manager.model.cluster.identities import IMMUTABLE_SELECTION_REL, ImmutableSelection, load_immutable_selection
from ambiguity_manager.model.errors import ModelBackendUnavailableError, ModelClientError
from ambiguity_manager.model.protocol import (
    GenerateJsonRequest,
    GenerateJsonResult,
    ModelRuntimeSpec,
    monotonic_ms,
)

LIFECYCLE_CREATED = "created"
LIFECYCLE_STARTED = "started"
LIFECYCLE_FAILED = "failed"
LIFECYCLE_CLOSED = "closed"

RUNTIME_CONFIG_REL = "configs/cluster/t12_vllm_batch_runtime.json"


class VllmBatchBackendError(ModelClientError):
    """Raised when vLLM batch backend validation or lifecycle rules fail."""


@dataclass(frozen=True)
class VllmBatchBackendConfig:
    schema_version: str
    backend_identifier: str
    immutable_selection_rel: str
    inference_environment_rel: str
    batch_size: int
    generation: dict[str, Any]
    engine: dict[str, Any]
    offline_only: bool
    network_fallback_permitted: bool

    @property
    def config_hash(self) -> str:
        return sha256_hex(canonical_json_bytes(self.to_dict()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "backend_identifier": self.backend_identifier,
            "references": {
                "immutable_selection": self.immutable_selection_rel,
                "inference_environment": self.inference_environment_rel,
            },
            "batch_size": self.batch_size,
            "generation": self.generation,
            "engine": self.engine,
            "offline_only": self.offline_only,
            "network_fallback_permitted": self.network_fallback_permitted,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VllmBatchBackendConfig:
        errors = validate_runtime_config(data)
        if errors:
            raise VllmBatchBackendError("; ".join(errors))
        refs = data.get("references", {})
        return cls(
            schema_version=str(data["schema_version"]),
            backend_identifier=str(data["backend_identifier"]),
            immutable_selection_rel=str(refs["immutable_selection"]),
            inference_environment_rel=str(refs["inference_environment"]),
            batch_size=int(data["batch_size"]),
            generation=dict(data["generation"]),
            engine=dict(data["engine"]),
            offline_only=bool(data["offline_only"]),
            network_fallback_permitted=bool(data["network_fallback_permitted"]),
        )


@dataclass(frozen=True)
class BatchRequest:
    request_id: str
    prompt: str
    ordinal: int
    synthetic: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BatchGenerationResult:
    request_id: str
    ordinal: int
    raw_text: str
    backend_identifier: str
    model_repository: str
    model_revision: str
    generation_status: str
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: float | None
    error_type: str | None
    error_message: str | None
    metadata: dict[str, Any]
    config_hash: str
    engine_request_id: str | int | None = None


EngineFactory = Callable[..., Any]
SamplingParamsFactory = Callable[[dict[str, Any]], Any]


def _extract_engine_request_id(engine_output: Any) -> str | int | None:
    if isinstance(engine_output, dict):
        engine_id = engine_output.get("request_id")
    else:
        engine_id = getattr(engine_output, "request_id", None)
    return engine_id


def _attach_engine_request_id(
    result: BatchGenerationResult,
    engine_request_id: str | int | None,
) -> BatchGenerationResult:
    if engine_request_id is None:
        return result
    return replace(result, engine_request_id=engine_request_id)


def validate_runtime_config(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != "1.0.0":
        errors.append("runtime_config.schema_version must be 1.0.0")
    if not data.get("backend_identifier"):
        errors.append("runtime_config.backend_identifier is required")
    refs = data.get("references")
    if not isinstance(refs, dict):
        errors.append("runtime_config.references must be an object")
    else:
        for key in ("immutable_selection", "inference_environment"):
            if not refs.get(key):
                errors.append(f"runtime_config.references.{key} is required")
    batch_size = data.get("batch_size")
    if not isinstance(batch_size, int) or batch_size <= 0:
        errors.append("runtime_config.batch_size must be a positive integer")
    generation = data.get("generation")
    if not isinstance(generation, dict):
        errors.append("runtime_config.generation must be an object")
    engine = data.get("engine")
    if not isinstance(engine, dict):
        errors.append("runtime_config.engine must be an object")
    elif engine.get("tensor_parallel_size") != 1:
        errors.append("runtime_config.engine.tensor_parallel_size must be 1")
    if data.get("offline_only") is not True:
        errors.append("runtime_config.offline_only must be true")
    if data.get("network_fallback_permitted") is True:
        errors.append("runtime_config.network_fallback_permitted must be false")
    return errors


def load_runtime_config(path: Path | str, *, repo_root: Path | None = None) -> VllmBatchBackendConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise VllmBatchBackendError(f"runtime_config_missing:{config_path}")
    import json

    data = json.loads(config_path.read_text(encoding="utf-8"))
    return VllmBatchBackendConfig.from_dict(data)


def load_runtime_config_from_repo(relpath: str = RUNTIME_CONFIG_REL, *, repo_root: Path | None = None) -> VllmBatchBackendConfig:
    from ambiguity_manager.model.cluster._config_loader import repo_root as _repo_root

    root = repo_root or _repo_root()
    return load_runtime_config(root / relpath, repo_root=root)


def _import_vllm_module() -> Any:
    try:
        return importlib.import_module("vllm")
    except ImportError as exc:
        raise ModelBackendUnavailableError(
            "vLLM is not installed; install vLLM in the cluster container before starting the batch backend"
        ) from exc


def validate_batch_requests(requests: list[BatchRequest]) -> None:
    seen: set[str] = set()
    for request in requests:
        if request.request_id in seen:
            raise VllmBatchBackendError(f"duplicate_request_id:{request.request_id}")
        seen.add(request.request_id)
        if not isinstance(request.prompt, str) or not request.prompt.strip():
            raise VllmBatchBackendError("blank_prompt")
        if request.ordinal < 0:
            raise VllmBatchBackendError(f"missing_or_invalid_ordinal:{request.request_id}")
        if request.synthetic is not True:
            raise VllmBatchBackendError("non_synthetic_request_rejected")


def normalize_engine_output(
    *,
    request: BatchRequest,
    engine_output: Any,
    backend_identifier: str,
    model_repository: str,
    model_revision: str,
    config_hash: str,
    latency_ms: float | None,
) -> BatchGenerationResult:
    outputs = getattr(engine_output, "outputs", None)
    if outputs is None and isinstance(engine_output, dict):
        outputs = engine_output.get("outputs")
    if not outputs:
        return _failure_result(
            request=request,
            backend_identifier=backend_identifier,
            model_repository=model_repository,
            model_revision=model_revision,
            config_hash=config_hash,
            error_type="malformed_engine_output",
            error_message="engine output missing completions",
            latency_ms=latency_ms,
        )
    if len(outputs) != 1:
        return _failure_result(
            request=request,
            backend_identifier=backend_identifier,
            model_repository=model_repository,
            model_revision=model_revision,
            config_hash=config_hash,
            error_type="multiple_completions",
            error_message="exactly one completion per request is required",
            latency_ms=latency_ms,
        )

    completion = outputs[0]
    raw_text = getattr(completion, "text", None)
    if raw_text is None and isinstance(completion, dict):
        raw_text = completion.get("text")
    if not isinstance(raw_text, str):
        return _failure_result(
            request=request,
            backend_identifier=backend_identifier,
            model_repository=model_repository,
            model_revision=model_revision,
            config_hash=config_hash,
            error_type="malformed_engine_output",
            error_message="completion text missing",
            latency_ms=latency_ms,
        )

    finish_reason = getattr(completion, "finish_reason", None)
    if finish_reason is None and isinstance(completion, dict):
        finish_reason = completion.get("finish_reason")

    prompt_tokens = getattr(completion, "prompt_tokens", None)
    if prompt_tokens is None and isinstance(completion, dict):
        prompt_tokens = completion.get("prompt_tokens")
    completion_tokens = getattr(completion, "completion_tokens", None)
    if completion_tokens is None and isinstance(completion, dict):
        completion_tokens = completion.get("completion_tokens")

    return BatchGenerationResult(
        request_id=request.request_id,
        ordinal=request.ordinal,
        raw_text=raw_text,
        backend_identifier=backend_identifier,
        model_repository=model_repository,
        model_revision=model_revision,
        generation_status="success",
        finish_reason=str(finish_reason) if finish_reason is not None else None,
        prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None,
        completion_tokens=completion_tokens if isinstance(completion_tokens, int) else None,
        latency_ms=latency_ms,
        error_type=None,
        error_message=None,
        metadata=dict(request.metadata),
        config_hash=config_hash,
    )


def _failure_result(
    *,
    request: BatchRequest,
    backend_identifier: str,
    model_repository: str,
    model_revision: str,
    config_hash: str,
    error_type: str,
    error_message: str,
    latency_ms: float | None,
    raw_text: str = "",
    engine_request_id: str | int | None = None,
) -> BatchGenerationResult:
    return BatchGenerationResult(
        request_id=request.request_id,
        ordinal=request.ordinal,
        raw_text=raw_text,
        backend_identifier=backend_identifier,
        model_repository=model_repository,
        model_revision=model_revision,
        generation_status="failure",
        finish_reason=None,
        prompt_tokens=None,
        completion_tokens=None,
        latency_ms=latency_ms,
        error_type=error_type,
        error_message=error_message,
        metadata=dict(request.metadata),
        config_hash=config_hash,
        engine_request_id=engine_request_id,
    )


class VllmBatchBackend:
    """One persistent vLLM engine per process with lazy dependency loading."""

    def __init__(
        self,
        config: VllmBatchBackendConfig,
        *,
        repo_root: Path | None = None,
        immutable: ImmutableSelection | None = None,
        engine_factory: EngineFactory | None = None,
        sampling_params_factory: SamplingParamsFactory | None = None,
    ) -> None:
        from ambiguity_manager.model.cluster._config_loader import repo_root as _repo_root

        self._config = config
        self._repo_root = repo_root or _repo_root()
        self._immutable = immutable or load_immutable_selection(self._repo_root)
        self._engine_factory = engine_factory
        self._sampling_params_factory = sampling_params_factory
        self._engine: Any | None = None
        self._lifecycle_state = LIFECYCLE_CREATED
        self._startup_error: str | None = None
        self._environment = load_json_config(config.inference_environment_rel, root=self._repo_root)

    @property
    def lifecycle_state(self) -> str:
        return self._lifecycle_state

    @property
    def runtime(self) -> ModelRuntimeSpec:
        return ModelRuntimeSpec(
            backend=self._config.backend_identifier,
            model_id=self._immutable.model_repository,
            immutable_revision=self._immutable.model_revision,
            tokenizer_revision=self._immutable.tokenizer_revision,
            quantisation="none",
            environment_id=str(self._environment.get("environment_id", "t12-cluster-inference")),
            device_policy="cuda_single_gpu",
        )

    def start(self) -> None:
        if self._lifecycle_state == LIFECYCLE_STARTED:
            return
        if self._lifecycle_state in {LIFECYCLE_FAILED, LIFECYCLE_CLOSED}:
            raise VllmBatchBackendError(f"backend_unusable:{self._startup_error or self._lifecycle_state}")
        try:
            self._engine = self._create_engine()
        except ModelBackendUnavailableError:
            self._lifecycle_state = LIFECYCLE_FAILED
            raise
        except Exception as exc:  # noqa: BLE001 - startup failure must be explicit
            self._lifecycle_state = LIFECYCLE_FAILED
            self._startup_error = str(exc)
            raise VllmBatchBackendError(f"engine_startup_failed:{exc}") from exc
        self._lifecycle_state = LIFECYCLE_STARTED

    def close(self) -> None:
        self._lifecycle_state = LIFECYCLE_CLOSED
        self._engine = None

    def generate_batch(self, requests: list[BatchRequest]) -> list[BatchGenerationResult]:
        if self._lifecycle_state != LIFECYCLE_STARTED or self._engine is None:
            raise VllmBatchBackendError("backend_not_started")
        validate_batch_requests(requests)
        if not requests:
            return []

        ordered = sorted(requests, key=lambda item: item.ordinal)
        sampling_params = self._build_sampling_params()
        results: list[BatchGenerationResult] = []
        for chunk_start in range(0, len(ordered), self._config.batch_size):
            chunk = ordered[chunk_start : chunk_start + self._config.batch_size]
            prompts = [item.prompt for item in chunk]
            started = time.perf_counter()
            engine_outputs = self._engine.generate(prompts, sampling_params)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            per_request_latency = elapsed_ms / len(chunk) if chunk else None
            mapped: dict[str, BatchGenerationResult] = {}
            if not isinstance(engine_outputs, (list, tuple)):
                for request in chunk:
                    mapped[request.request_id] = _failure_result(
                        request=request,
                        backend_identifier=self._config.backend_identifier,
                        model_repository=self._immutable.model_repository,
                        model_revision=self._immutable.model_revision,
                        config_hash=self._config.config_hash,
                        error_type="malformed_engine_output",
                        error_message="engine output is not a sequence",
                        latency_ms=per_request_latency,
                    )
            elif len(engine_outputs) < len(chunk):
                for request in chunk:
                    mapped[request.request_id] = _failure_result(
                        request=request,
                        backend_identifier=self._config.backend_identifier,
                        model_repository=self._immutable.model_repository,
                        model_revision=self._immutable.model_revision,
                        config_hash=self._config.config_hash,
                        error_type="missing_engine_output",
                        error_message="engine returned fewer outputs than prompts",
                        latency_ms=per_request_latency,
                    )
            elif len(engine_outputs) > len(chunk):
                for request in chunk:
                    mapped[request.request_id] = _failure_result(
                        request=request,
                        backend_identifier=self._config.backend_identifier,
                        model_repository=self._immutable.model_repository,
                        model_revision=self._immutable.model_revision,
                        config_hash=self._config.config_hash,
                        error_type="excess_engine_output",
                        error_message="engine returned more outputs than prompts",
                        latency_ms=per_request_latency,
                    )
            else:
                caller_ids = {request.request_id for request in chunk}
                for index, request in enumerate(chunk):
                    engine_output = engine_outputs[index]
                    engine_request_id = _extract_engine_request_id(engine_output)
                    if (
                        engine_request_id is not None
                        and str(engine_request_id) in caller_ids
                        and str(engine_request_id) != request.request_id
                    ):
                        mapped[request.request_id] = _failure_result(
                            request=request,
                            backend_identifier=self._config.backend_identifier,
                            model_repository=self._immutable.model_repository,
                            model_revision=self._immutable.model_revision,
                            config_hash=self._config.config_hash,
                            error_type="engine_output_order_mismatch",
                            error_message=(
                                f"engine output id {engine_request_id!r} matches another caller request "
                                f"at position {index}"
                            ),
                            latency_ms=per_request_latency,
                            engine_request_id=engine_request_id,
                        )
                        continue
                    result = normalize_engine_output(
                        request=request,
                        engine_output=engine_output,
                        backend_identifier=self._config.backend_identifier,
                        model_repository=self._immutable.model_repository,
                        model_revision=self._immutable.model_revision,
                        config_hash=self._config.config_hash,
                        latency_ms=per_request_latency,
                    )
                    mapped[request.request_id] = _attach_engine_request_id(result, engine_request_id)
            for request in chunk:
                results.append(mapped[request.request_id])
        return sorted(results, key=lambda item: item.ordinal)

    def generate_json(self, request: GenerateJsonRequest) -> GenerateJsonResult:
        if not request.metadata.get("synthetic"):
            raise VllmBatchBackendError("non_synthetic_request_rejected")
        user_prompt = next(
            (message["content"] for message in request.messages if message["role"] == "user"),
            "",
        )
        batch_request = BatchRequest(
            request_id=request.run_id or request.fixture_id or "request",
            prompt=user_prompt,
            ordinal=0,
            synthetic=True,
            metadata=dict(request.metadata),
        )
        if self._lifecycle_state != LIFECYCLE_STARTED:
            self.start()
        started = monotonic_ms()
        batch_result = self.generate_batch([batch_request])[0]
        latency_ms = batch_result.latency_ms if batch_result.latency_ms is not None else monotonic_ms() - started
        final_status = "success" if batch_result.generation_status == "success" else "generation_failed"
        return GenerateJsonResult.from_runtime(
            runtime=self.runtime,
            request_id=batch_request.request_id,
            raw_output=batch_result.raw_text,
            extracted_json_text=None,
            parsed_object=None,
            schema_valid=False,
            schema_errors=[batch_result.error_message] if batch_result.error_message else [],
            repair_attempts=0,
            repair_log=[],
            final_status=final_status,
            latency_ms=latency_ms,
            prompt_tokens=batch_result.prompt_tokens,
            completion_tokens=batch_result.completion_tokens,
            runtime_metadata={
                "backend_impl": "vllm_batch",
                "finish_reason": batch_result.finish_reason,
                "config_hash": batch_result.config_hash,
            },
        )

    def _create_engine(self) -> Any:
        if self._engine_factory is not None:
            return self._engine_factory(
                model=self._immutable.model_repository,
                revision=self._immutable.model_revision,
                engine_settings=self._config.engine,
                offline_only=self._config.offline_only,
            )
        vllm = _import_vllm_module()
        llm_cls = getattr(vllm, "LLM")
        engine_kwargs = {
            "model": self._immutable.model_repository,
            "revision": self._immutable.model_revision,
            "tensor_parallel_size": int(self._config.engine.get("tensor_parallel_size", 1)),
            "trust_remote_code": False,
        }
        if "gpu_memory_utilization" in self._config.engine:
            engine_kwargs["gpu_memory_utilization"] = float(self._config.engine["gpu_memory_utilization"])
        return llm_cls(**engine_kwargs)

    def _build_sampling_params(self) -> Any:
        generation = self._config.generation
        if self._sampling_params_factory is not None:
            return self._sampling_params_factory(generation)
        vllm = _import_vllm_module()
        sampling_cls = getattr(vllm, "SamplingParams")
        return sampling_cls(
            temperature=float(generation.get("temperature", 0.1)),
            top_p=float(generation.get("top_p", 1.0)),
            max_tokens=int(generation.get("max_tokens", 2048)),
        )


def create_vllm_batch_backend(
    config: VllmBatchBackendConfig,
    *,
    repo_root: Path | None = None,
    immutable: ImmutableSelection | None = None,
    engine_factory: EngineFactory | None = None,
    sampling_params_factory: SamplingParamsFactory | None = None,
) -> VllmBatchBackend:
    return VllmBatchBackend(
        config,
        repo_root=repo_root,
        immutable=immutable,
        engine_factory=engine_factory,
        sampling_params_factory=sampling_params_factory,
    )
