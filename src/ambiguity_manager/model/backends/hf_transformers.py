"""Lazy optional Hugging Face backend boundary."""

from __future__ import annotations

from ambiguity_manager.model.errors import ModelBackendUnavailableError
from ambiguity_manager.model.protocol import ModelClient, ModelRuntimeSpec


def create_hf_backend(runtime: ModelRuntimeSpec) -> ModelClient:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError as exc:
        raise ModelBackendUnavailableError(
            "hf_transformers_local backend requires optional ML dependencies"
        ) from exc

    raise ModelBackendUnavailableError(
        "hf_transformers_local backend is not implemented until the GPU environment slice"
    )
