"""CPU-only tests for T12 Stage D1B2 pinned vLLM structured-output adapter."""

from __future__ import annotations

import copy
import importlib
import json
import sys
import unittest
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.prediction_contract import DERIVATION_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_REL = "configs/model/t12_structured_decode_contract.json"
SCHEMA_REL = "configs/model/schema/t12_model_semantic_output.schema.json"
EXPECTED_SCHEMA_HASH = "232235fec53ee38eafcd714fd53664b250e848a6b0f75fca1ff7ec903b08cfb4"
REQUIRED_VLLM_VERSION = "0.20.1"


def _load_json(relpath: str) -> dict[str, Any]:
    return json.loads((REPO_ROOT / relpath).read_text(encoding="utf-8"))


def _generation_config(**overrides: object) -> dict[str, Any]:
    base: dict[str, Any] = {
        "temperature": 0.1,
        "top_p": 0.95,
        "max_tokens": 512,
    }
    base.update(overrides)
    return base


class FakeStructuredOutputs:
    instances: list["FakeStructuredOutputs"] = []

    def __init__(self, *, json: dict[str, Any], **kwargs: Any) -> None:
        self.json = json
        self.regex = None
        self.choice = None
        self.grammar = None
        self.json_object = None
        self.structural_tag = None
        self.kwargs = {"json": json, **kwargs}
        FakeStructuredOutputs.instances.append(self)


class FakeSamplingParams:
    instances: list["FakeSamplingParams"] = []

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
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.n = n
        self.structured_outputs = structured_outputs
        self.kwargs = {
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "n": n,
            "structured_outputs": structured_outputs,
            **kwargs,
        }
        FakeSamplingParams.instances.append(self)


class SamplingParamsWithoutStructuredOutputs:
    def __init__(self, *, temperature: float, top_p: float, max_tokens: int, n: int = 1) -> None:
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.n = n


class StructuredOutputsWithoutJson:
    def __init__(self, *, schema: dict[str, Any]) -> None:
        self.schema = schema


@dataclass
class GeneratedDataclassStructuredOutputs:
    json: dict[str, Any] | None = None
    regex: str | None = None
    choice: list[str] | None = None
    grammar: str | None = None
    json_object: bool | None = None
    structural_tag: str | None = None


def _generic_generated_init(self: GeneratedDataclassStructuredOutputs, *args: object, **kwargs: object) -> None:
    self.json = kwargs.get("json")  # type: ignore[assignment]
    self.regex = None
    self.choice = None
    self.grammar = None
    self.json_object = None
    self.structural_tag = None


GeneratedDataclassStructuredOutputs.__init__ = _generic_generated_init  # type: ignore[method-assign]


class AnnotatedStructuredOutputs:
    json: dict[str, Any]

    def __init__(self, **kwargs: object) -> None:
        self.json = kwargs["json"]  # type: ignore[assignment]


class KwargsOnlyStructuredOutputs:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.json = kwargs.get("json")


class DictReplacementStructuredOutputs:
    def __init__(self, *, json: dict[str, Any]) -> None:
        self.payload = json

    @property
    def json(self) -> dict[str, Any]:
        return self.payload


class T12StructuredDecodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.structured_decode = importlib.import_module(
            "ambiguity_manager.model.structured_decode"
        )
        cls.contract_payload = _load_json(CONTRACT_REL)
        cls.contract = cls.structured_decode.load_structured_decode_contract(
            REPO_ROOT / CONTRACT_REL
        )

    def setUp(self) -> None:
        FakeStructuredOutputs.instances.clear()
        FakeSamplingParams.instances.clear()

    def test_module_imports_without_vllm_installed(self) -> None:
        self.assertFalse(hasattr(self.structured_decode, "_VLLM_MODULE"))
        self.assertTrue(hasattr(self.structured_decode, "build_structured_sampling_params"))

    def test_package_import_does_not_load_torch_vllm_transformers(self) -> None:
        for name in list(sys.modules):
            if name.startswith(("torch", "vllm", "transformers")):
                del sys.modules[name]
        import ambiguity_manager.model  # noqa: F401

        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("vllm", sys.modules)
        self.assertNotIn("transformers", sys.modules)

    def test_exact_contract_loads(self) -> None:
        self.assertEqual(self.contract.contract_version, "1.0.0")
        self.assertEqual(self.contract.required_vllm_version, REQUIRED_VLLM_VERSION)
        self.assertEqual(self.contract.structured_output_field_name, "structured_outputs")
        self.assertEqual(self.contract.schema_parameter_name, "json")
        self.assertEqual(self.contract.semantic_schema_sha256, EXPECTED_SCHEMA_HASH)
        self.assertEqual(self.contract.derivation_version, DERIVATION_VERSION)
        self.assertEqual(self.contract.completions_per_request, 1)
        self.assertFalse(self.contract.lossy_schema_adaptation_permitted)
        self.assertFalse(self.contract.unconstrained_fallback_permitted)
        self.assertFalse(self.contract.guided_decoding_permitted)
        self.assertEqual(
            self.contract.response_mode_status,
            "unverified_until_pinned_runtime_inspection",
        )
        self.assertEqual(
            self.contract.engine_time_schema_compilation_status,
            "unverified_until_stage_d2",
        )

    def test_exact_schema_hash_passes(self) -> None:
        schema = self.structured_decode.load_verified_semantic_schema(
            self.contract,
            repo_root=REPO_ROOT,
        )
        observed = sha256_hex(canonical_json_bytes(schema))
        self.assertEqual(observed, EXPECTED_SCHEMA_HASH)

    def test_altered_schema_hash_fails(self) -> None:
        bad_contract = replace(self.contract, semantic_schema_sha256="0" * 64)
        with self.assertRaises(self.structured_decode.SchemaIdentityMismatchError):
            self.structured_decode.load_verified_semantic_schema(
                bad_contract,
                repo_root=REPO_ROOT,
            )

    def test_wrong_derivation_version_fails(self) -> None:
        bad_contract = replace(self.contract, derivation_version="t12-d1a-0.0.0")
        with self.assertRaises(self.structured_decode.SchemaIdentityMismatchError):
            self.structured_decode.load_verified_semantic_schema(
                bad_contract,
                repo_root=REPO_ROOT,
            )

    def test_invalid_draft202012_schema_fails(self) -> None:
        with self.assertRaises(self.structured_decode.SchemaInvalidError):
            self.structured_decode.validate_semantic_schema_document({"type": "not-a-valid-type"})

    def test_wrong_vllm_version_fails(self) -> None:
        generation = _generation_config()
        with self.assertRaises(self.structured_decode.WrongVllmVersionError):
            self.structured_decode.build_structured_sampling_params(
                generation,
                self.contract,
                repo_root=REPO_ROOT,
                sampling_params_class=FakeSamplingParams,
                structured_outputs_class=FakeStructuredOutputs,
                detected_vllm_version="0.19.0",
            )

    def test_missing_sampling_params_class_fails(self) -> None:
        generation = _generation_config()

        class BrokenModule:
            pass

        with self.assertRaises(self.structured_decode.MissingApiClassError):
            self.structured_decode.build_structured_sampling_params(
                generation,
                self.contract,
                repo_root=REPO_ROOT,
                sampling_params_class=None,
                structured_outputs_class=FakeStructuredOutputs,
                detected_vllm_version=REQUIRED_VLLM_VERSION,
                sampling_params_resolver=lambda _module: None,
            )

    def test_missing_structured_outputs_class_fails(self) -> None:
        generation = _generation_config()
        with self.assertRaises(self.structured_decode.MissingApiClassError):
            self.structured_decode.build_structured_sampling_params(
                generation,
                self.contract,
                repo_root=REPO_ROOT,
                sampling_params_class=FakeSamplingParams,
                structured_outputs_class=None,
                detected_vllm_version=REQUIRED_VLLM_VERSION,
                structured_outputs_resolver=lambda _module: None,
            )

    def test_missing_structured_outputs_field_fails(self) -> None:
        generation = _generation_config()
        with self.assertRaises(self.structured_decode.MissingApiFieldError):
            self.structured_decode.build_structured_sampling_params(
                generation,
                self.contract,
                repo_root=REPO_ROOT,
                sampling_params_class=SamplingParamsWithoutStructuredOutputs,
                structured_outputs_class=FakeStructuredOutputs,
                detected_vllm_version=REQUIRED_VLLM_VERSION,
            )

    def test_missing_json_field_fails(self) -> None:
        generation = _generation_config()
        with self.assertRaises(self.structured_decode.MissingApiFieldError):
            self.structured_decode.build_structured_sampling_params(
                generation,
                self.contract,
                repo_root=REPO_ROOT,
                sampling_params_class=FakeSamplingParams,
                structured_outputs_class=StructuredOutputsWithoutJson,
                detected_vllm_version=REQUIRED_VLLM_VERSION,
            )

    def test_fake_structured_class_receives_exact_schema_dictionary(self) -> None:
        generation = _generation_config()
        expected_schema = self.structured_decode.load_verified_semantic_schema(
            self.contract,
            repo_root=REPO_ROOT,
        )
        self.structured_decode.build_structured_sampling_params(
            generation,
            self.contract,
            repo_root=REPO_ROOT,
            sampling_params_class=FakeSamplingParams,
            structured_outputs_class=FakeStructuredOutputs,
            detected_vllm_version=REQUIRED_VLLM_VERSION,
        )
        self.assertEqual(len(FakeStructuredOutputs.instances), 1)
        self.assertEqual(FakeStructuredOutputs.instances[0].kwargs["json"], expected_schema)

    def test_fake_sampling_params_receives_structured_outputs(self) -> None:
        generation = _generation_config()
        result = self.structured_decode.build_structured_sampling_params(
            generation,
            self.contract,
            repo_root=REPO_ROOT,
            sampling_params_class=FakeSamplingParams,
            structured_outputs_class=FakeStructuredOutputs,
            detected_vllm_version=REQUIRED_VLLM_VERSION,
        )
        self.assertIn("structured_outputs", FakeSamplingParams.instances[0].kwargs)
        self.assertIs(
            FakeSamplingParams.instances[0].kwargs["structured_outputs"],
            FakeStructuredOutputs.instances[0],
        )
        self.assertIs(result.sampling_params, FakeSamplingParams.instances[0])

    def test_fake_sampling_params_receives_n_equals_one(self) -> None:
        generation = _generation_config()
        self.structured_decode.build_structured_sampling_params(
            generation,
            self.contract,
            repo_root=REPO_ROOT,
            sampling_params_class=FakeSamplingParams,
            structured_outputs_class=FakeStructuredOutputs,
            detected_vllm_version=REQUIRED_VLLM_VERSION,
        )
        self.assertEqual(FakeSamplingParams.instances[0].kwargs["n"], 1)

    def test_generation_values_propagate_exactly(self) -> None:
        generation = _generation_config(temperature=0.25, top_p=0.8, max_tokens=1024)
        self.structured_decode.build_structured_sampling_params(
            generation,
            self.contract,
            repo_root=REPO_ROOT,
            sampling_params_class=FakeSamplingParams,
            structured_outputs_class=FakeStructuredOutputs,
            detected_vllm_version=REQUIRED_VLLM_VERSION,
        )
        kwargs = FakeSamplingParams.instances[0].kwargs
        self.assertEqual(kwargs["temperature"], 0.25)
        self.assertEqual(kwargs["top_p"], 0.8)
        self.assertEqual(kwargs["max_tokens"], 1024)

    def test_caller_configuration_is_not_mutated(self) -> None:
        generation = _generation_config()
        original = copy.deepcopy(generation)
        self.structured_decode.build_structured_sampling_params(
            generation,
            self.contract,
            repo_root=REPO_ROOT,
            sampling_params_class=FakeSamplingParams,
            structured_outputs_class=FakeStructuredOutputs,
            detected_vllm_version=REQUIRED_VLLM_VERSION,
        )
        self.assertEqual(generation, original)

    def test_no_fallback_to_guided_decoding(self) -> None:
        generation = _generation_config()
        self.structured_decode.build_structured_sampling_params(
            generation,
            self.contract,
            repo_root=REPO_ROOT,
            sampling_params_class=FakeSamplingParams,
            structured_outputs_class=FakeStructuredOutputs,
            detected_vllm_version=REQUIRED_VLLM_VERSION,
        )
        kwargs = FakeSamplingParams.instances[0].kwargs
        self.assertNotIn("guided_decoding", kwargs)

    def test_no_unconstrained_fallback_on_construction_failure(self) -> None:
        generation = _generation_config()

        class BrokenStructuredOutputs:
            def __init__(self, *, json: dict[str, Any]) -> None:
                raise RuntimeError("construction failed")

        with self.assertRaises(self.structured_decode.ParameterConstructionError):
            self.structured_decode.build_structured_sampling_params(
                generation,
                self.contract,
                repo_root=REPO_ROOT,
                sampling_params_class=FakeSamplingParams,
                structured_outputs_class=BrokenStructuredOutputs,
                detected_vllm_version=REQUIRED_VLLM_VERSION,
            )
        self.assertEqual(len(FakeSamplingParams.instances), 0)

    def test_contract_hash_is_deterministic(self) -> None:
        first = self.structured_decode.structured_decode_contract_hash(self.contract)
        second = self.structured_decode.structured_decode_contract_hash(self.contract)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_construction_metadata_is_deterministic(self) -> None:
        generation = _generation_config()
        first = self.structured_decode.build_structured_sampling_params(
            generation,
            self.contract,
            repo_root=REPO_ROOT,
            sampling_params_class=FakeSamplingParams,
            structured_outputs_class=FakeStructuredOutputs,
            detected_vllm_version=REQUIRED_VLLM_VERSION,
        )
        second = self.structured_decode.build_structured_sampling_params(
            generation,
            self.contract,
            repo_root=REPO_ROOT,
            sampling_params_class=FakeSamplingParams,
            structured_outputs_class=FakeStructuredOutputs,
            detected_vllm_version=REQUIRED_VLLM_VERSION,
        )
        self.assertEqual(first.metadata.to_dict(), second.metadata.to_dict())
        self.assertEqual(first.metadata.construction_status, "constructed")
        self.assertEqual(first.metadata.schema_hash, EXPECTED_SCHEMA_HASH)
        self.assertEqual(first.metadata.completions_per_request, 1)

    def test_dataclass_json_accepted_when_generated_init_hides_field(self) -> None:
        import inspect

        generation = _generation_config()
        signature = inspect.signature(GeneratedDataclassStructuredOutputs.__init__)
        self.assertNotIn("json", signature.parameters)
        discovery = self.structured_decode._discover_constructor_field(
            GeneratedDataclassStructuredOutputs,
            "json",
        )
        self.assertTrue(discovery.present)
        self.assertEqual(discovery.method, "dataclass_fields")
        result = self.structured_decode.build_structured_sampling_params(
            generation,
            self.contract,
            repo_root=REPO_ROOT,
            sampling_params_class=FakeSamplingParams,
            structured_outputs_class=GeneratedDataclassStructuredOutputs,
            detected_vllm_version=REQUIRED_VLLM_VERSION,
        )
        expected_schema = self.structured_decode.load_verified_semantic_schema(
            self.contract,
            repo_root=REPO_ROOT,
        )
        structured = result.sampling_params.kwargs["structured_outputs"]
        self.assertEqual(structured.json, expected_schema)
        self.assertEqual(result.metadata.construction_status, "constructed")

    def test_dataclass_field_discovery_reports_dataclass_fields(self) -> None:
        discovery = self.structured_decode._discover_constructor_field(
            GeneratedDataclassStructuredOutputs,
            "json",
        )
        self.assertEqual(discovery.method, "dataclass_fields")

    def test_class_annotation_discovery_works(self) -> None:
        discovery = self.structured_decode._discover_constructor_field(
            AnnotatedStructuredOutputs,
            "json",
        )
        self.assertTrue(discovery.present)
        self.assertEqual(discovery.method, "class_annotations")

    def test_class_signature_discovery_works_for_normal_class(self) -> None:
        discovery = self.structured_decode._discover_constructor_field(
            FakeStructuredOutputs,
            "json",
        )
        self.assertTrue(discovery.present)
        self.assertEqual(discovery.method, "class_signature")

    def test_kwargs_only_class_without_declared_field_is_rejected(self) -> None:
        discovery = self.structured_decode._discover_constructor_field(
            KwargsOnlyStructuredOutputs,
            "json",
        )
        self.assertFalse(discovery.present)
        generation = _generation_config()
        with self.assertRaises(self.structured_decode.MissingApiFieldError):
            self.structured_decode.build_structured_sampling_params(
                generation,
                self.contract,
                repo_root=REPO_ROOT,
                sampling_params_class=FakeSamplingParams,
                structured_outputs_class=KwargsOnlyStructuredOutputs,
                detected_vllm_version=REQUIRED_VLLM_VERSION,
            )

    def test_competing_constraint_fields_must_remain_null(self) -> None:
        generation = _generation_config()
        result = self.structured_decode.build_structured_sampling_params(
            generation,
            self.contract,
            repo_root=REPO_ROOT,
            sampling_params_class=FakeSamplingParams,
            structured_outputs_class=GeneratedDataclassStructuredOutputs,
            detected_vllm_version=REQUIRED_VLLM_VERSION,
        )
        structured = result.sampling_params.kwargs["structured_outputs"]
        for field_name in (
            "regex",
            "choice",
            "grammar",
            "json_object",
            "structural_tag",
        ):
            self.assertIsNone(getattr(structured, field_name))

    def test_no_plain_dictionary_structured_output_replacement_path(self) -> None:
        generation = _generation_config()

        class DictSubstitutingSamplingParams:
            def __init__(
                self,
                *,
                temperature: float,
                top_p: float,
                max_tokens: int,
                n: int,
                structured_outputs: Any,
            ) -> None:
                self.temperature = temperature
                self.top_p = top_p
                self.max_tokens = max_tokens
                self.n = n
                self.structured_outputs = {"json": structured_outputs}

        with self.assertRaises(self.structured_decode.ParameterConstructionError):
            self.structured_decode.build_structured_sampling_params(
                generation,
                self.contract,
                repo_root=REPO_ROOT,
                sampling_params_class=DictSubstitutingSamplingParams,
                structured_outputs_class=FakeStructuredOutputs,
                detected_vllm_version=REQUIRED_VLLM_VERSION,
            )


if __name__ == "__main__":
    unittest.main()
