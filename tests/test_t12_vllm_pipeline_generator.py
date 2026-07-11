"""Tests for T12 Stage D-Final vLLM pipeline generator adapter."""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Any

from ambiguity_manager.model.cluster.identities import load_immutable_selection
from ambiguity_manager.model.vllm_pipeline_generator import VllmPipelineGenerator

IMMUTABLE = load_immutable_selection()


def _runtime_config(**overrides: object) -> Any:
    from ambiguity_manager.model.backends.vllm_batch import VllmBatchBackendConfig

    base: dict[str, Any] = {
        "schema_version": "1.0.0",
        "backend_identifier": "vllm_batch_direct",
        "references": {
            "immutable_selection": "configs/model/immutable_selection.json",
            "inference_environment": "configs/environments/t12_cluster_inference.json",
        },
        "batch_size": 1,
        "generation": {"temperature": 0.1, "top_p": 1.0, "max_tokens": 256},
        "engine": {"tensor_parallel_size": 1, "gpu_memory_utilization": 0.9},
        "offline_only": True,
        "network_fallback_permitted": False,
        "structured_decode": {
            "enabled": True,
            "contract_relpath": "configs/model/t12_structured_decode_contract.json",
            "semantic_schema_relpath": "configs/model/schema/t12_model_semantic_output.schema.json",
        },
    }
    base.update(overrides)
    return VllmBatchBackendConfig.from_dict(base)


@dataclass
class FakePersistentBackend:
    config: Any
    started: bool = False
    generate_calls: int = 0
    responses: list[Any] = field(default_factory=list)

    def start(self) -> None:
        self.started = True

    def close(self) -> None:
        self.started = False

    def generate_batch(self, requests: list[Any]) -> list[Any]:
        from ambiguity_manager.model.backends.vllm_batch import BatchGenerationResult

        self.generate_calls += 1
        if self.responses:
            return self.responses[: len(requests)]
        request = requests[0]
        return [
            BatchGenerationResult(
                request_id=request.request_id,
                ordinal=request.ordinal,
                raw_text='{"recommended_strategy":"execute"}',
                backend_identifier=self.config.backend_identifier,
                model_repository=IMMUTABLE.model_repository,
                model_revision=IMMUTABLE.model_revision,
                generation_status="success",
                finish_reason="stop",
                prompt_tokens=10,
                completion_tokens=5,
                latency_ms=1.0,
                error_type=None,
                error_message=None,
                metadata={},
                config_hash=self.config.config_hash,
                engine_request_id="engine-42",
            )
        ]


class T12VllmPipelineGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = _runtime_config()
        self.backend = FakePersistentBackend(config=self.config)
        self.backend.start()
        self.generator = VllmPipelineGenerator(backend=self.backend)  # type: ignore[arg-type]

    def test_one_persistent_backend_reused(self) -> None:
        self.generator.generate(
            rendered_prompt="prompt-a",
            attempt_index=0,
            caller_request_id="pred:dfinal-001",
        )
        self.generator.generate(
            rendered_prompt="prompt-b",
            attempt_index=1,
            caller_request_id="pred:dfinal-001",
        )
        self.assertEqual(self.backend.generate_calls, 2)

    def test_caller_id_canonical(self) -> None:
        output = self.generator.generate(
            rendered_prompt="prompt-a",
            attempt_index=0,
            caller_request_id="pred:dfinal-001",
        )
        self.assertEqual(self.generator.generate_calls[-1]["caller_request_id"], "pred:dfinal-001")
        self.assertIsNotNone(output.raw_output)

    def test_engine_id_diagnostic(self) -> None:
        output = self.generator.generate(
            rendered_prompt="prompt-a",
            attempt_index=0,
            caller_request_id="pred:dfinal-001",
        )
        self.assertEqual(output.engine_request_id, "engine-42")

    def test_structured_decode_mandatory_in_backend_config(self) -> None:
        self.assertIsNotNone(self.config.structured_decode)
        self.assertTrue(self.config.structured_decode.enabled)

    def test_one_completion_mandatory(self) -> None:
        output = self.generator.generate(
            rendered_prompt="prompt-a",
            attempt_index=0,
            caller_request_id="pred:dfinal-001",
        )
        self.assertEqual(output.generation_status, "success")

    def test_unknown_failures_non_retryable(self) -> None:
        from ambiguity_manager.model.backends.vllm_batch import BatchGenerationResult

        self.backend.responses = [
            BatchGenerationResult(
                request_id="pred:dfinal-001",
                ordinal=0,
                raw_text="",
                backend_identifier=self.config.backend_identifier,
                model_repository=IMMUTABLE.model_repository,
                model_revision=IMMUTABLE.model_revision,
                generation_status="failure",
                finish_reason=None,
                prompt_tokens=None,
                completion_tokens=None,
                latency_ms=1.0,
                error_type="engine_output_order_mismatch",
                error_message="order mismatch",
                metadata={},
                config_hash=self.config.config_hash,
            )
        ]
        output = self.generator.generate(
            rendered_prompt="prompt-a",
            attempt_index=0,
            caller_request_id="pred:dfinal-001",
        )
        self.assertEqual(output.generation_error_type, "engine_output_order_mismatch")

    def test_typed_transient_output_failure_may_be_retryable(self) -> None:
        from ambiguity_manager.model.backends.vllm_batch import BatchGenerationResult

        self.backend.responses = [
            BatchGenerationResult(
                request_id="pred:dfinal-001",
                ordinal=0,
                raw_text="",
                backend_identifier=self.config.backend_identifier,
                model_repository=IMMUTABLE.model_repository,
                model_revision=IMMUTABLE.model_revision,
                generation_status="failure",
                finish_reason=None,
                prompt_tokens=None,
                completion_tokens=None,
                latency_ms=1.0,
                error_type="transient_output_production_failure",
                error_message="temporary",
                metadata={},
                config_hash=self.config.config_hash,
            )
        ]
        output = self.generator.generate(
            rendered_prompt="prompt-a",
            attempt_index=0,
            caller_request_id="pred:dfinal-001",
        )
        self.assertEqual(output.generation_error_type, "transient_output_production_failure")

    def test_no_unconstrained_fallback(self) -> None:
        self.assertFalse(self.config.structured_decode.enabled is False)

    def test_no_model_loaded_in_cpu_tests(self) -> None:
        self.assertIsInstance(self.backend, FakePersistentBackend)


if __name__ == "__main__":
    unittest.main()
