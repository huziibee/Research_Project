"""Standalone factory for bound local model clients."""

from __future__ import annotations

from ambiguity_manager.model.errors import ModelBackendUnavailableError, ModelClientError
from ambiguity_manager.model.protocol import ModelClient, ModelRuntimeSpec

SUPPORTED_BACKENDS = frozenset({"fake", "hf_transformers_local"})


def create_model_client(runtime: ModelRuntimeSpec) -> ModelClient:
    if runtime.backend not in SUPPORTED_BACKENDS:
        raise ModelClientError(f"unsupported backend: {runtime.backend}")

    if not runtime.immutable_revision or len(runtime.immutable_revision) < 8:
        raise ModelClientError("immutable_revision must be a non-empty commit SHA")
    if not runtime.tokenizer_revision or len(runtime.tokenizer_revision) < 8:
        raise ModelClientError("tokenizer_revision must be a non-empty commit SHA")

    if runtime.backend == "fake":
        from ambiguity_manager.model.backends.fake import FakeBackend

        return FakeBackend(runtime)

    if runtime.backend == "hf_transformers_local":
        from ambiguity_manager.model.backends.hf_transformers import create_hf_backend

        return create_hf_backend(runtime)

    raise ModelBackendUnavailableError(f"backend unavailable: {runtime.backend}")
