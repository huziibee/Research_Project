"""CPU-only tests for T12 persistent vLLM batch backend (Stage C2A)."""

from __future__ import annotations

import importlib
import json
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ambiguity_manager.model.errors import ModelBackendUnavailableError
from ambiguity_manager.model.protocol import GenerateJsonRequest, ModelRuntimeSpec
from ambiguity_manager.model.cluster.identities import _EXPECTED
from ambiguity_manager.schema.v2.json_schema import build_prediction_json_schema

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE_D_RUNTIME_REL = "configs/cluster/t12_stage_d_vllm_runtime.json"


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
    request_id: str | int | None
    outputs: list[FakeCompletion] = field(default_factory=list)
    prompt_token_ids: list[int] = field(default_factory=list)


class FakeEngine:
    instances: list["FakeEngine"] = []

    def __init__(self, **_kwargs: Any) -> None:
        self.generate_calls = 0
        self.closed = False
        self.last_sampling_params: Any | None = None
        FakeEngine.instances.append(self)

    def generate(self, prompts: list[str], sampling_params: Any) -> list[FakeRequestOutput]:
        self.generate_calls += 1
        self.last_sampling_params = sampling_params
        results: list[FakeRequestOutput] = []
        for index, prompt in enumerate(prompts):
            results.append(
                FakeRequestOutput(
                    request_id=str(index),
                    outputs=[FakeCompletion(text=f"raw:{prompt}")],
                )
            )
        return results


class FakeStructuredOutputs:
    instances: list["FakeStructuredOutputs"] = []

    def __init__(self, *, json: dict[str, Any], **kwargs: Any) -> None:
        self.kwargs = {"json": json, **kwargs}
        FakeStructuredOutputs.instances.append(self)


class FakeStructuredSamplingParams:
    instances: list["FakeStructuredSamplingParams"] = []

    def __init__(
        self,
        *,
        temperature: float,
        top_p: float,
        max_tokens: int,
        n: int,
        structured_outputs: Any,
        **kwargs: Any,
    ) -> None:
        self.kwargs = {
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "n": n,
            "structured_outputs": structured_outputs,
            **kwargs,
        }
        FakeStructuredSamplingParams.instances.append(self)


class T12VllmBatchBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeEngine.instances.clear()
        FakeStructuredOutputs.instances.clear()
        FakeStructuredSamplingParams.instances.clear()
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

    def test_string_numeric_engine_ids_map_positionally(self) -> None:
        backend = self._backend()
        backend.start()
        results = backend.generate_batch(
            [
                self._request(request_id="request-A", ordinal=0, prompt="first"),
                self._request(request_id="request-B", ordinal=1, prompt="second"),
            ]
        )
        self.assertEqual([item.request_id for item in results], ["request-A", "request-B"])
        self.assertEqual([item.ordinal for item in results], [0, 1])
        self.assertEqual(results[0].raw_text, "raw:first")
        self.assertEqual(results[1].raw_text, "raw:second")
        self.assertEqual(results[0].engine_request_id, "0")
        self.assertEqual(results[1].engine_request_id, "1")

    def test_integer_engine_ids_map_positionally(self) -> None:
        class IntegerIdEngine(FakeEngine):
            def generate(self, prompts, sampling_params):  # type: ignore[no-untyped-def]
                self.generate_calls += 1
                return [
                    FakeRequestOutput(request_id=index, outputs=[FakeCompletion(text=f"raw:{prompt}")])
                    for index, prompt in enumerate(prompts)
                ]

        backend = self._backend(engine_factory=lambda **_k: IntegerIdEngine())
        backend.start()
        results = backend.generate_batch(
            [
                self._request(request_id="request-A", ordinal=0, prompt="first"),
                self._request(request_id="request-B", ordinal=1, prompt="second"),
            ]
        )
        self.assertEqual([item.request_id for item in results], ["request-A", "request-B"])
        self.assertEqual(results[0].generation_status, "success")
        self.assertEqual(results[1].generation_status, "success")
        self.assertEqual(results[0].engine_request_id, 0)
        self.assertEqual(results[1].engine_request_id, 1)

    def test_opaque_engine_ids_map_positionally(self) -> None:
        class OpaqueIdEngine(FakeEngine):
            def generate(self, prompts, sampling_params):  # type: ignore[no-untyped-def]
                self.generate_calls += 1
                return [
                    FakeRequestOutput(
                        request_id=f"engine-{index}-{prompt[:3]}",
                        outputs=[FakeCompletion(text=f"raw:{prompt}")],
                    )
                    for index, prompt in enumerate(prompts)
                ]

        backend = self._backend(engine_factory=lambda **_k: OpaqueIdEngine())
        backend.start()
        results = backend.generate_batch(
            [
                self._request(request_id="request-A", ordinal=0, prompt="alpha"),
                self._request(request_id="request-B", ordinal=1, prompt="beta"),
            ]
        )
        self.assertEqual([item.request_id for item in results], ["request-A", "request-B"])
        self.assertEqual(results[0].generation_status, "success")
        self.assertEqual(results[1].generation_status, "success")
        self.assertEqual(results[0].engine_request_id, "engine-0-alp")
        self.assertEqual(results[1].engine_request_id, "engine-1-bet")

    def test_absent_engine_ids_map_positionally_and_remain_null(self) -> None:
        class AbsentIdEngine(FakeEngine):
            def generate(self, prompts, sampling_params):  # type: ignore[no-untyped-def]
                self.generate_calls += 1
                return [
                    FakeRequestOutput(request_id=None, outputs=[FakeCompletion(text=f"raw:{prompt}")])
                    for prompt in prompts
                ]

        backend = self._backend(engine_factory=lambda **_k: AbsentIdEngine())
        backend.start()
        results = backend.generate_batch(
            [
                self._request(request_id="request-A", ordinal=0, prompt="first"),
                self._request(request_id="request-B", ordinal=1, prompt="second"),
            ]
        )
        self.assertEqual([item.request_id for item in results], ["request-A", "request-B"])
        self.assertIsNone(results[0].engine_request_id)
        self.assertIsNone(results[1].engine_request_id)

    def test_numeric_engine_ids_do_not_produce_unknown_output_id(self) -> None:
        class GlobalCounterEngine(FakeEngine):
            counter = 0

            def generate(self, prompts, sampling_params):  # type: ignore[no-untyped-def]
                self.generate_calls += 1
                outputs: list[FakeRequestOutput] = []
                for prompt in prompts:
                    outputs.append(
                        FakeRequestOutput(
                            request_id=GlobalCounterEngine.counter,
                            outputs=[FakeCompletion(text=f"raw:{prompt}")],
                        )
                    )
                    GlobalCounterEngine.counter += 1
                return outputs

        GlobalCounterEngine.counter = 7
        backend = self._backend(engine_factory=lambda **_k: GlobalCounterEngine())
        backend.start()
        results = backend.generate_batch(
            [
                self._request(request_id="request-A", ordinal=0, prompt="first"),
                self._request(request_id="request-B", ordinal=1, prompt="second"),
            ]
        )
        self.assertEqual(results[0].generation_status, "success")
        self.assertEqual(results[1].generation_status, "success")
        self.assertNotEqual(results[0].error_type, "unknown_output_id")
        self.assertNotEqual(results[1].error_type, "unknown_output_id")

    def test_four_requests_in_two_backend_calls_correlate_correctly(self) -> None:
        class GlobalCounterEngine(FakeEngine):
            counter = 0

            def generate(self, prompts, sampling_params):  # type: ignore[no-untyped-def]
                self.generate_calls += 1
                outputs: list[FakeRequestOutput] = []
                for prompt in prompts:
                    outputs.append(
                        FakeRequestOutput(
                            request_id=GlobalCounterEngine.counter,
                            outputs=[FakeCompletion(text=f"raw:{prompt}")],
                        )
                    )
                    GlobalCounterEngine.counter += 1
                return outputs

        GlobalCounterEngine.counter = 100
        backend = self._backend(engine_factory=lambda **_k: GlobalCounterEngine())
        backend.start()
        results = backend.generate_batch(
            [
                self._request(request_id="req-0", ordinal=0, prompt="p0"),
                self._request(request_id="req-1", ordinal=1, prompt="p1"),
                self._request(request_id="req-2", ordinal=2, prompt="p2"),
                self._request(request_id="req-3", ordinal=3, prompt="p3"),
            ]
        )
        self.assertEqual(len(results), 4)
        self.assertEqual([item.request_id for item in results], ["req-0", "req-1", "req-2", "req-3"])
        self.assertTrue(all(item.generation_status == "success" for item in results))
        self.assertEqual(FakeEngine.instances[0].generate_calls, 2)

    def test_more_outputs_than_inputs_fail_explicitly(self) -> None:
        class ExtraOutputEngine(FakeEngine):
            def generate(self, prompts, sampling_params):  # type: ignore[no-untyped-def]
                self.generate_calls += 1
                return [
                    FakeRequestOutput(request_id="0", outputs=[FakeCompletion(text="a")]),
                    FakeRequestOutput(request_id="1", outputs=[FakeCompletion(text="b")]),
                ]

        backend = self._backend(engine_factory=lambda **_k: ExtraOutputEngine())
        backend.start()
        results = backend.generate_batch([self._request()])
        self.assertEqual(results[0].generation_status, "failure")
        self.assertIn("excess_engine_output", results[0].error_type or "")

    def test_engine_output_order_mismatch_when_caller_id_at_wrong_position(self) -> None:
        class WrongOrderEngine(FakeEngine):
            def generate(self, prompts, sampling_params):  # type: ignore[no-untyped-def]
                self.generate_calls += 1
                return [
                    FakeRequestOutput(request_id="request-B", outputs=[FakeCompletion(text="raw:first")]),
                    FakeRequestOutput(request_id="request-A", outputs=[FakeCompletion(text="raw:second")]),
                ]

        backend = self._backend(engine_factory=lambda **_k: WrongOrderEngine())
        backend.start()
        results = backend.generate_batch(
            [
                self._request(request_id="request-A", ordinal=0, prompt="first"),
                self._request(request_id="request-B", ordinal=1, prompt="second"),
            ]
        )
        self.assertEqual(results[0].generation_status, "failure")
        self.assertIn("engine_output_order_mismatch", results[0].error_type or "")

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


class T12VllmBatchStructuredDecodeIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeEngine.instances.clear()
        FakeStructuredOutputs.instances.clear()
        FakeStructuredSamplingParams.instances.clear()
        from ambiguity_manager.model.backends import vllm_batch

        self.vllm_batch = importlib.reload(vllm_batch)
        self.stage_d_config = self.vllm_batch.VllmBatchBackendConfig.from_dict(
            json.loads((REPO_ROOT / STAGE_D_RUNTIME_REL).read_text(encoding="utf-8"))
        )

    def _structured_backend(self, **kwargs: Any):
        return self.vllm_batch.VllmBatchBackend(
            self.stage_d_config,
            repo_root=REPO_ROOT,
            engine_factory=kwargs.pop("engine_factory", lambda **_k: FakeEngine()),
            sampling_params_factory=kwargs.pop("sampling_params_factory", None),
            **kwargs,
        )

    def _patch_structured_adapter(self) -> None:
        structured_decode = importlib.import_module("ambiguity_manager.model.structured_decode")

        def _fake_build(generation_config, contract, **kwargs: Any):
            schema = structured_decode.load_verified_semantic_schema(
                contract,
                repo_root=kwargs.get("repo_root", REPO_ROOT),
            )
            structured_outputs = FakeStructuredOutputs(json=schema)
            sampling_params = FakeStructuredSamplingParams(
                temperature=float(generation_config["temperature"]),
                top_p=float(generation_config["top_p"]),
                max_tokens=int(generation_config["max_tokens"]),
                n=1,
                structured_outputs=structured_outputs,
            )
            metadata = structured_decode.StructuredDecodeMetadata(
                contract_hash=structured_decode.structured_decode_contract_hash(contract),
                schema_hash=contract.semantic_schema_sha256,
                sampling_params_module=contract.sampling_params_module,
                sampling_params_class=contract.sampling_params_class,
                structured_outputs_module=contract.structured_outputs_module,
                structured_outputs_class=contract.structured_outputs_class,
                structured_output_field_name=contract.structured_output_field_name,
                schema_parameter_name=contract.schema_parameter_name,
                required_vllm_version=contract.required_vllm_version,
                detected_vllm_version=contract.required_vllm_version,
                completions_per_request=1,
                construction_status="constructed",
                response_mode_status=contract.response_mode_status,
                engine_time_schema_compilation_status=contract.engine_time_schema_compilation_status,
            )
            return structured_decode.StructuredDecodeBuildResult(
                sampling_params=sampling_params,
                metadata=metadata,
            )

        self._fake_build = _fake_build
        self._structured_decode_module = structured_decode
        self._original_build = structured_decode.build_structured_sampling_params
        structured_decode.build_structured_sampling_params = _fake_build

    def tearDown(self) -> None:
        if hasattr(self, "_structured_decode_module"):
            self._structured_decode_module.build_structured_sampling_params = self._original_build

    def test_stage_c_configuration_still_builds_ordinary_sampling_params(self) -> None:
        captured: dict[str, Any] = {}

        def factory(generation: dict[str, Any]) -> object:
            captured["generation"] = generation
            return object()

        backend = self.vllm_batch.VllmBatchBackend(
            self.vllm_batch.VllmBatchBackendConfig.from_dict(_runtime_config_dict()),
            engine_factory=lambda **_k: FakeEngine(),
            sampling_params_factory=factory,
        )
        backend.start()
        backend.generate_batch(
            [
                self.vllm_batch.BatchRequest(
                    request_id="req-1",
                    prompt="hello",
                    ordinal=0,
                    synthetic=True,
                )
            ]
        )
        self.assertIn("temperature", captured["generation"])
        self.assertNotIn("structured_decode", captured)

    def test_stage_d_configuration_invokes_adapter(self) -> None:
        self._patch_structured_adapter()
        backend = self._structured_backend()
        backend.start()
        backend.generate_batch(
            [
                self.vllm_batch.BatchRequest(
                    request_id="req-1",
                    prompt="structured",
                    ordinal=0,
                    synthetic=True,
                )
            ]
        )
        self.assertEqual(len(FakeStructuredSamplingParams.instances), 1)
        self.assertEqual(len(FakeStructuredOutputs.instances), 1)
        self.assertIn("structured_outputs", FakeStructuredSamplingParams.instances[0].kwargs)
        metadata = backend.last_structured_decode_metadata
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["construction_status"], "constructed")
        self.assertEqual(metadata["completions_per_request"], 1)

    def test_adapter_failure_prevents_engine_generation(self) -> None:
        self._patch_structured_adapter()

        def failing_build(*_args: Any, **_kwargs: Any):
            raise self._structured_decode_module.SchemaIdentityMismatchError("schema mismatch")

        self._structured_decode_module.build_structured_sampling_params = failing_build
        backend = self._structured_backend()
        backend.start()
        with self.assertRaises(self.vllm_batch.VllmBatchBackendError) as ctx:
            backend.generate_batch(
                [
                    self.vllm_batch.BatchRequest(
                        request_id="req-1",
                        prompt="structured",
                        ordinal=0,
                        synthetic=True,
                    )
                ]
            )
        self.assertIn("structured_decode_schema_identity_mismatch", str(ctx.exception))
        self.assertEqual(FakeEngine.instances[0].generate_calls, 0)

    def test_structured_output_construction_once_per_batch_invocation(self) -> None:
        self._patch_structured_adapter()
        build_calls: list[dict[str, Any]] = []

        def counting_build(generation_config, contract, **kwargs: Any):
            build_calls.append(dict(generation_config))
            return self._fake_build(generation_config, contract, **kwargs)

        self._structured_decode_module.build_structured_sampling_params = counting_build
        backend = self._structured_backend()
        backend.start()
        backend.generate_batch(
            [
                self.vllm_batch.BatchRequest(request_id="a", prompt="one", ordinal=0, synthetic=True),
                self.vllm_batch.BatchRequest(request_id="b", prompt="two", ordinal=1, synthetic=True),
                self.vllm_batch.BatchRequest(request_id="c", prompt="three", ordinal=2, synthetic=True),
            ]
        )
        self.assertEqual(len(build_calls), 1)
        expected_engine_calls = -(-3 // self.stage_d_config.batch_size)
        self.assertEqual(FakeEngine.instances[0].generate_calls, expected_engine_calls)

    def test_exactly_one_completion_remains_enforced(self) -> None:
        self._patch_structured_adapter()
        backend = self._structured_backend()
        backend.start()
        backend.generate_batch(
            [
                self.vllm_batch.BatchRequest(
                    request_id="req-1",
                    prompt="structured",
                    ordinal=0,
                    synthetic=True,
                )
            ]
        )
        self.assertEqual(FakeStructuredSamplingParams.instances[0].kwargs["n"], 1)

    def test_injected_sampling_factory_still_supported_with_stage_d_config(self) -> None:
        captured: list[dict[str, Any]] = []

        def factory(generation: dict[str, Any]) -> object:
            captured.append(dict(generation))
            return object()

        backend = self._structured_backend(sampling_params_factory=factory)
        backend.start()
        backend.generate_batch(
            [
                self.vllm_batch.BatchRequest(
                    request_id="req-1",
                    prompt="factory",
                    ordinal=0,
                    synthetic=True,
                )
            ]
        )
        self.assertEqual(len(captured), 1)
        self.assertEqual(len(FakeStructuredSamplingParams.instances), 0)


if __name__ == "__main__":
    unittest.main()
