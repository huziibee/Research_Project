"""Optional model backends."""

from __future__ import annotations

from ambiguity_manager.model.backends.vllm_batch import (
    BatchGenerationResult,
    BatchRequest,
    VllmBatchBackend,
    VllmBatchBackendConfig,
    create_vllm_batch_backend,
    load_runtime_config,
)

__all__ = [
    "BatchGenerationResult",
    "BatchRequest",
    "VllmBatchBackend",
    "VllmBatchBackendConfig",
    "create_vllm_batch_backend",
    "load_runtime_config",
]
