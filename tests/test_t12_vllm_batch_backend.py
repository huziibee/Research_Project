"""CPU-only tests for T12 persistent vLLM batch backend (Stage C2A)."""

from __future__ import annotations

import importlib
import sys
import unittest
from dataclasses import dataclass, field
from typing import Any

from ambiguity_manager.model.errors import ModelBackendUnavailableError
from ambiguity_manager.model.protocol import GenerateJsonRequest, ModelRuntimeSpec
from ambiguity_manager.model.cluster.identities import _EXPECTED
from ambiguity_manager.schema.v2.json_schema import build_prediction_json_schema


def _runtime_config_dict(**overrides: object) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": "1.0.0",
        "backend_identifier": "vllm_batch_direct",
        "references": {
            "immutable_selection": "configs/model/immutable_selection.json",
            "inference_environment": "configs/environments/t12_cluster_inference.json",
        },
        "batch_size": 2,
        "generation": {
            "temperature": 0.1,
            "top_p": 1.0,
            "max_tokens": 256,
            "verification_status": "unverified_until_stage_c2b",
        },
        "engine": {
            "tensor_parallel_size": 1,
            "gpu_memory_utilization": 0.9,
            "verification_status": "unverified_until_stage_c2b",
        },
        "offline_only": True,
        "network_fallback_permitted": False,
    }
    base.update(overrides)
    return base


@dataclass
class FakeCompletion:
    text: str
    finish_reason: str = "stop"
    prompt_tokens: int | None = 10
    completion_tokens: int | None = 5


@dataclass
class FakeRequestOutput:
    request_id: str
    outputs: list[FakeCompletion] = field(default_factory=list)
    prompt_token_ids: list[int] = field(default_factory=list)


class FakeEngine:
    instances: list["FakeEngine"] = []

    def __init__(self, **_kwargs: Any) -> None:
        self.generate_calls = 0
        self.closed = False
        FakeEngine.instances.append(self)

    def generate(self, prompts: list[str], sampling_params: Any) -> list[FakeRequestOutput]:
        self.generate_calls += 1
        results: list[FakeRequestOutput] = []
        for index, prompt in enumerate(prompts):
            results.append(
                FakeRequestOutput(
                    request_id=str(index),
                    outputs=[FakeCompletion(text=f"raw:{prompt}")],
                )
            )
        return results


class T12VllmBatchBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeEngine.instances.clear()
        from ambiguity_manager.model.backends import vllm_batch

        self.vllm_batch = importlib.reload(vllm_batch)
        self.config = self.vllm_batch.VllmBatchBackendConfig.from_dict(_runtime_config_dict())

    def _backend(self, **kwargs: Any):
        return self.vllm_batch.VllmBatchBackend(
            self.config,
            engine_factory=kwargs.pop("engine_factory", lambda **_k: FakeEngine()),
            sampling_params_factory=kwargs.pop(
                "sampling_params_factory", lambda _generation: object()
            ),
            **kwargs,
        )

    def _request(self, request_id: str = "req-1", ordinal: int = 0, prompt: str = "hello"):
        return self.vllm_batch.BatchRequest(
            request_id=request_id,
            prompt=prompt,
            ordinal=ordinal,
            synthetic=True,
        )

    def test_module_imports_without_vllm_installed(self) -> None:
        self.assertFalse(hasattr(self.vllm_batch, "_VLLM_MODULE"))
        self.assertEqual(self.vllm_batch.VllmBatchBackend.__name__, "VllmBatchBackend")

    def test_package_import_does_not_load_torch_or_vllm(self) -> None:
        for name in list(sys.modules):
            if name.startswith(("torch", "vllm", "transformers")):
                del sys.modules[name]
        import ambiguity_manager.model  # noqa: F401

        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("vllm", sys.modules)
        self.assertNotIn("transformers", sys.modules)

    def test_real_start_without_vllm_gives_precise_dependency_error(self) -> None:
        backend = self.vllm_batch.VllmBatchBackend(self.config, engine_factory=None)
        with self.assertRaises(ModelBackendUnavailableError) as ctx:
            backend.start()
        self.assertIn("vLLM", str(ctx.exception))

    def test_injected_factory_starts_once(self) -> None:
        backend = self._backend()
        backend.start()
        self.assertEqual(backend.lifecycle_state, "started")
        self.assertEqual(len(FakeEngine.instances), 1)

    def test_repeated_start_does_not_create_another_engine(self) -> None:
        backend = self._backend()
        backend.start()
        backend.start()
        self.assertEqual(len(FakeEngine.instances), 1)

    def test_two_batch_calls_reuse_one_engine(self) -> None:
        backend = self._backend()
        backend.start()
        backend.generate_batch([self._request()])
        backend.generate_batch([self._request(request_id="req-2", ordinal=1)])
        self.assertEqual(len(FakeEngine.instances), 1)
        self.assertEqual(FakeEngine.instances[0].generate_calls, 2)

    def test_generation_before_start_fails(self) -> None:
        backend = self._backend()
        with self.assertRaises(self.vllm_batch.VllmBatchBackendError):
            backend.generate_batch([self._request()])

    def test_duplicate_request_ids_fail_before_engine_call(self) -> None:
        backend = self._backend()
        backend.start()
        with self.assertRaises(self.vllm_batch.VllmBatchBackendError):
            backend.generate_batch(
                [
                    self._request(request_id="dup", ordinal=0),
                    self._request(request_id="dup", ordinal=1),
                ]
            )
        self.assertEqual(FakeEngine.instances[0].generate_calls, 0)

    def test_blank_prompt_fails(self) -> None:
        backend = self._backend()
        backend.start()
        with self.assertRaises(self.vllm_batch.VllmBatchBackendError):
            backend.generate_batch([self._request(prompt="   ")])

    def test_non_synthetic_request_fails(self) -> None:
        backend = self._backend()
        backend.start()
        bad = self.vllm_batch.BatchRequest(
            request_id="req-x",
            prompt="hello",
            ordinal=0,
            synthetic=False,
        )
        with self.assertRaises(self.vllm_batch.VllmBatchBackendError):
            backend.generate_batch([bad])

    def test_output_order_follows_ordinal(self) -> None:
        backend = self._backend()
        backend.start()
        results = backend.generate_batch(
            [
                self._request(request_id="b", ordinal=1, prompt="second"),
                self._request(request_id="a", ordinal=0, prompt="first"),
            ]
        )
        self.assertEqual([item.ordinal for item in results], [0, 1])
        self.assertEqual([item.request_id for item in results], ["a", "b"])

    def test_missing_engine_output_becomes_explicit_failure(self) -> None:
        class EmptyEngine(FakeEngine):
            def generate(self, prompts, sampling_params):  # type: ignore[no-untyped-def]
                self.generate_calls += 1
                return []

        backend = self._backend(engine_factory=lambda **_k: EmptyEngine())
        backend.start()
        results = backend.generate_batch([self._request()])
        self.assertEqual(results[0].generation_status, "failure")
        self.assertIn("missing_engine_output", results[0].error_type or "")

    def test_unknown_output_id_fails(self) -> None:
        class BadIdEngine(FakeEngine):
            def generate(self, prompts, sampling_params):  # type: ignore[no-untyped-def]
                self.generate_calls += 1
                return [FakeRequestOutput(request_id="unexpected", outputs=[FakeCompletion(text="x")])]

        backend = self._backend(engine_factory=lambda **_k: BadIdEngine())
        backend.start()
        results = backend.generate_batch([self._request(request_id="expected")])
        self.assertEqual(results[0].generation_status, "failure")
        self.assertIn("unknown_output_id", results[0].error_type or "")

    def test_malformed_output_becomes_explicit_failure(self) -> None:
        class MalformedEngine(FakeEngine):
            def generate(self, prompts, sampling_params):  # type: ignore[no-untyped-def]
                self.generate_calls += 1
                return [FakeRequestOutput(request_id="0", outputs=[])]

        backend = self._backend(engine_factory=lambda **_k: MalformedEngine())
        backend.start()
        results = backend.generate_batch([self._request()])
        self.assertEqual(results[0].generation_status, "failure")
        self.assertIn("malformed_engine_output", results[0].error_type or "")

    def test_raw_text_preserved_exactly(self) -> None:
        backend = self._backend()
        backend.start()
        results = backend.generate_batch([self._request(prompt="preserve me")])
        self.assertEqual(results[0].raw_text, "raw:preserve me")

    def test_unavailable_token_counts_remain_unavailable(self) -> None:
        class NoTokenEngine(FakeEngine):
            def generate(self, prompts, sampling_params):  # type: ignore[no-untyped-def]
                self.generate_calls += 1
                return [
                    FakeRequestOutput(
                        request_id="0",
                        outputs=[FakeCompletion(text="x", prompt_tokens=None, completion_tokens=None)],
                    )
                ]

        backend = self._backend(engine_factory=lambda **_k: NoTokenEngine())
        backend.start()
        results = backend.generate_batch([self._request()])
        self.assertIsNone(results[0].prompt_tokens)
        self.assertIsNone(results[0].completion_tokens)

    def test_backend_config_hash_is_deterministic(self) -> None:
        first = self.vllm_batch.VllmBatchBackendConfig.from_dict(_runtime_config_dict())
        second = self.vllm_batch.VllmBatchBackendConfig.from_dict(_runtime_config_dict())
        self.assertEqual(first.config_hash, second.config_hash)

    def test_more_than_one_completion_is_rejected(self) -> None:
        class MultiCompletionEngine(FakeEngine):
            def generate(self, prompts, sampling_params):  # type: ignore[no-untyped-def]
                self.generate_calls += 1
                return [
                    FakeRequestOutput(
                        request_id="0",
                        outputs=[FakeCompletion(text="a"), FakeCompletion(text="b")],
                    )
                ]

        backend = self._backend(engine_factory=lambda **_k: MultiCompletionEngine())
        backend.start()
        results = backend.generate_batch([self._request()])
        self.assertEqual(results[0].generation_status, "failure")
        self.assertIn("multiple_completions", results[0].error_type or "")

    def test_model_client_generate_json_compatibility(self) -> None:
        backend = self._backend()
        backend.start()
        request = GenerateJsonRequest(
            messages=[{"role": "user", "content": "cluster prompt"}],
            json_schema=build_prediction_json_schema(),
            fixture_id="syn-001",
            run_id="req-model-client",
            metadata={"synthetic": True},
        )
        result = backend.generate_json(request)
        self.assertEqual(result.request_id, "req-model-client")
        self.assertEqual(result.raw_output, "raw:cluster prompt")
        self.assertEqual(result.backend, "vllm_batch_direct")
        self.assertEqual(result.model_id, _EXPECTED["model_repository"])


if __name__ == "__main__":
    unittest.main()
