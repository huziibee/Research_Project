"""Tests for ModelClient protocol, runtime binding, and fake backend."""

from __future__ import annotations

import importlib
import sys
import unittest
from dataclasses import FrozenInstanceError

from ambiguity_manager.model.context_budget import (
    DEFAULT_SAFETY_MARGIN,
    ContextBudgetError,
    compute_effective_max_new_tokens,
)
from ambiguity_manager.model.errors import ModelClientError
from ambiguity_manager.model.factory import create_model_client
from ambiguity_manager.model.protocol import (
    GenerateJsonRequest,
    GenerateJsonResult,
    ModelRuntimeSpec,
    validate_messages,
)
from ambiguity_manager.schema.v2.json_schema import build_prediction_json_schema


def _runtime_spec(**overrides: object) -> ModelRuntimeSpec:
    base = {
        "backend": "fake",
        "model_id": "test/fake-model",
        "immutable_revision": "a" * 40,
        "tokenizer_revision": "a" * 40,
        "quantisation": "none",
        "environment_id": "t12-test",
        "device_policy": "cpu",
    }
    base.update(overrides)
    return ModelRuntimeSpec(**base)


class ModelClientTests(unittest.TestCase):
    def test_runtime_spec_immutable(self) -> None:
        spec = _runtime_spec()
        with self.assertRaises(FrozenInstanceError):
            spec.backend = "other"  # type: ignore[misc]

    def test_request_has_no_runtime_fields(self) -> None:
        fields = {f.name for f in GenerateJsonRequest.__dataclass_fields__.values()}
        forbidden = {
            "backend",
            "model_id",
            "immutable_revision",
            "tokenizer_revision",
            "quantisation",
            "environment_id",
            "device_policy",
        }
        self.assertFalse(forbidden & fields)

    def test_fake_backend_preserves_raw_output(self) -> None:
        client = create_model_client(_runtime_spec())
        request = GenerateJsonRequest(
            messages=[{"role": "user", "content": "emit json"}],
            json_schema=build_prediction_json_schema(),
            fixture_id="syn-001",
            run_id="run-1",
        )
        result = client.generate_json(request)
        self.assertIsInstance(result, GenerateJsonResult)
        self.assertTrue(result.raw_output)
        self.assertEqual(result.backend, "fake")
        self.assertEqual(result.model_id, "test/fake-model")
        self.assertEqual(result.immutable_revision, "a" * 40)

    def test_context_budget_calculation(self) -> None:
        effective = compute_effective_max_new_tokens(
            requested_max_new_tokens=2048,
            model_context_limit=4096,
            prompt_token_count=512,
            safety_margin=DEFAULT_SAFETY_MARGIN,
        )
        self.assertEqual(effective, min(2048, 4096 - 512 - DEFAULT_SAFETY_MARGIN))

    def test_insufficient_context_budget_raises(self) -> None:
        with self.assertRaises(ContextBudgetError):
            compute_effective_max_new_tokens(
                requested_max_new_tokens=100,
                model_context_limit=4096,
                prompt_token_count=4000,
            )

    def test_unknown_model_context_limit_raises(self) -> None:
        with self.assertRaises(ContextBudgetError):
            compute_effective_max_new_tokens(
                requested_max_new_tokens=100,
                model_context_limit=None,
                prompt_token_count=10,
            )

    def test_unknown_prompt_token_count_raises(self) -> None:
        with self.assertRaises(ContextBudgetError):
            compute_effective_max_new_tokens(
                requested_max_new_tokens=100,
                model_context_limit=4096,
                prompt_token_count=None,
            )

    def test_validate_messages_rejects_empty_role(self) -> None:
        with self.assertRaises(ModelClientError):
            validate_messages([{"role": "", "content": "x"}])

    def test_import_ambiguity_manager_without_ml(self) -> None:
        for name in (
            "torch",
            "transformers",
            "peft",
            "trl",
            "accelerate",
            "bitsandbytes",
            "datasets",
        ):
            sys.modules.pop(name, None)
        import ambiguity_manager

        importlib.reload(ambiguity_manager)
        loaded = {k for k in sys.modules if k.startswith(("torch", "transformers", "peft", "trl", "bitsandbytes", "datasets"))}
        self.assertEqual(loaded, set())

    def test_hf_backend_stub_raises_without_importing_torch(self) -> None:
        sys.modules.pop("torch", None)
        with self.assertRaises(ModelClientError):
            create_model_client(_runtime_spec(backend="hf_transformers_local"))


if __name__ == "__main__":
    unittest.main()
