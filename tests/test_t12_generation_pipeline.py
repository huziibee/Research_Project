"""Tests for T12 Stage D1C1 bounded generation pipeline."""

from __future__ import annotations

import copy
import importlib
import json
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.attempt_evidence import defensive_copy_metadata
from ambiguity_manager.model.generation_pipeline import (
    ATTEMPT_KINDS,
    BackendIdentity,
    FailureCategory,
    GenerationAttemptGenerator,
    GenerationPipelineRequest,
    GenerationReadyPromptEnvelope,
    GenerationReadyRenderer,
    GeneratorOutput,
    PipelineFinalStatus,
    PipelineIntegrityContext,
    SEMANTIC_CORRECTNESS_NOT_EVALUATED,
    StructuredDecodeReadiness,
    empty_integrity_context,
    run_generation_pipeline,
    validate_integrity_context,
    validate_pipeline_request,
)
from ambiguity_manager.model.prediction_contract import (
    PredictionProvenancePolicy,
    default_synthetic_prediction_provenance_policy,
)
from ambiguity_manager.model.prompt_builder import compute_prompt_hash
from ambiguity_manager.model.response_mode import ResponseModeStatus
from ambiguity_manager.model.structured_decode import (
    StructuredDecodeMetadata,
    load_structured_decode_contract,
    structured_decode_contract_hash,
)
from ambiguity_manager.schema.v2.records import LabelEligibility
from ambiguity_manager.schema.v2.taxonomies import (
    CapabilityStatus,
    CPCSlotStatus,
    RiskLevel,
    RouteLabel,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
IMMUTABLE_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
MODEL_REPO = "Qwen/Qwen3-8B"
SYN003_INTEGRITY_RAW = {
    "fixture_id": "syn-003",
    "command": "Bring me the mug.",
    "scene_context": "kitchen counter with one blue mug",
    "dialogue_history": [],
    "capability_context": "robot can transport mugs",
    "support_declarations": {
        "supported_objects": ["blue mug", "mug"],
        "supported_locations": ["kitchen counter"],
        "supported_quantities": [],
        "supported_temporal_values": [],
        "supported_capabilities": ["transport mugs"],
        "supported_safety_facts": [],
        "valid_evidence_references": ["command", "scene_context", "capability_context"],
        "critical_slots": ["object"],
        "expected_route_pressure": "silently_resolve",
    },
}
SYN003_INTEGRITY = PipelineIntegrityContext.from_mapping(SYN003_INTEGRITY_RAW)
EMPTY_INTEGRITY = empty_integrity_context()


def _empty_cpc() -> dict[str, Any]:
    slot = {"value": None, "status": CPCSlotStatus.UNKNOWN.value}
    return {name: dict(slot) for name in (
        "action", "actor", "object", "object_attributes", "destination",
        "spatial_relation", "quantity", "time", "recipient", "tool",
        "conditions", "constraints", "negation",
    )}


def _complete_semantic(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "cpc": _empty_cpc(),
        "speech_act": None,
        "intent_summary": None,
        "candidate_interpretations": [],
        "selected_interpretation": None,
        "unresolved_slots": [],
        "supporting_evidence": [],
        "ambiguity_present": False,
        "ambiguity_types": [],
        "primary_ambiguity_type": None,
        "compound_ambiguity": False,
        "compound_ambiguity_count": 0,
        "risk_relevant": False,
        "risk_level": None,
        "capability_status": None,
        "recommended_strategy": RouteLabel.EXECUTE.value,
        "strategy_sequence": [],
        "clarification_question": None,
        "clarification_subtype": None,
        "clarification_targets": [],
        "rejection_reason": None,
        "resolved_slots": [],
        "resolution_method": None,
        "resolution_evidence": [],
        "context_sampling_uncertainty": None,
    }
    payload.update(overrides)
    return payload


def _evidence(source: str, span: str) -> dict[str, Any]:
    return {"source": source, "span": span, "note": None}


def _valid_silent_semantic() -> dict[str, Any]:
    return _complete_semantic(
        recommended_strategy=RouteLabel.SILENTLY_RESOLVE.value,
        selected_interpretation={
            "frame_id": "pred:syn-003:candidate:0",
            "supporting_evidence": [_evidence("scene_context", "blue mug")],
        },
        candidate_interpretations=[
            {
                "frame_id": "pred:syn-003:candidate:0",
                "text": "blue mug",
                "cpc": _empty_cpc(),
                "confidence": None,
                "safety_status": None,
            }
        ],
        resolved_slots=[{"slot_name": "object", "value": "blue mug"}],
        resolution_method="context_supported",
        resolution_evidence=[_evidence("scene_context", "blue mug")],
    )


def _json_output(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _pipeline_request(**overrides: object) -> GenerationPipelineRequest:
    defaults: dict[str, Any] = {
        "caller_request_id": "pred:syn-test-001",
        "synthetic": True,
        "command": "Pick up the cup.",
        "label_eligibility": LabelEligibility(
            routing=True,
            ambiguity=True,
            clarification_decision=True,
        ),
        "provenance_policy": default_synthetic_prediction_provenance_policy(),
        "source_dataset": "t12_synthetic",
        "integrity_context": EMPTY_INTEGRITY,
    }
    if "integrity_context" in overrides and isinstance(overrides["integrity_context"], dict):
        raw = overrides["integrity_context"]
        if not validate_integrity_context(raw):
            overrides["integrity_context"] = PipelineIntegrityContext.from_mapping(raw)
    defaults.update(overrides)
    return GenerationPipelineRequest(**defaults)


@dataclass
class FakeRenderer:
    verified: bool = True
    repository: str = MODEL_REPO
    revision: str = IMMUTABLE_REVISION
    render_calls: int = 0

    def render(self, messages: list[dict[str, str]]) -> GenerationReadyPromptEnvelope:
        self.render_calls += 1
        payload = [{"role": m["role"], "content": m["content"]} for m in messages]
        abstract_hash = sha256_hex(canonical_json_bytes({"messages": payload}))
        rendered = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        rendered_hash = sha256_hex(rendered.encode("utf-8"))
        return GenerationReadyPromptEnvelope(
            rendered_prompt_text=rendered,
            abstract_message_hash=abstract_hash,
            rendered_prompt_hash=rendered_hash,
            model_repository=self.repository,
            immutable_model_revision=self.revision,
            response_mode_status=(
                ResponseModeStatus.VERIFIED.value
                if self.verified
                else ResponseModeStatus.UNVERIFIED.value
            ),
            response_mode_method_identity="t12-d1c1-test-renderer",
            renderer_identity="fake-test-renderer",
            renderer_version="1.0.0",
        )


@dataclass
class FakeGenerator:
    outputs: list[Any] = field(default_factory=list)
    engine_ids: list[str | None] = field(default_factory=list)
    calls: list[int] = field(default_factory=list)
    raise_on_attempt: dict[int, Exception] = field(default_factory=dict)
    _index: int = 0

    def generate(
        self,
        *,
        rendered_prompt: str,
        attempt_index: int,
        caller_request_id: str,
    ) -> GeneratorOutput:
        if attempt_index in self.raise_on_attempt:
            raise self.raise_on_attempt[attempt_index]
        self.calls.append(attempt_index)
        item = self.outputs[min(self._index, len(self.outputs) - 1)]
        self._index += 1
        if isinstance(item, GeneratorOutput):
            return item
        engine_id = (
            self.engine_ids[min(self._index - 1, len(self.engine_ids) - 1)]
            if self.engine_ids
            else f"engine-{attempt_index}"
        )
        return GeneratorOutput(
            raw_output=str(item),
            engine_request_id=engine_id,
            finish_reason="stop",
            prompt_tokens=120,
            completion_tokens=80,
            runtime_metadata={"attempt": attempt_index},
        )


def _readiness(**overrides: object) -> StructuredDecodeReadiness:
    contract = load_structured_decode_contract(REPO_ROOT / "configs/model/t12_structured_decode_contract.json")
    metadata = StructuredDecodeMetadata(
        contract_hash=structured_decode_contract_hash(contract),
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
    defaults = {"metadata": metadata, "unconstrained_fallback_indicated": False}
    defaults.update(overrides)
    return StructuredDecodeReadiness(**defaults)


def _run(
    request: GenerationPipelineRequest,
    *,
    outputs: list[str],
    renderer: FakeRenderer | None = None,
    readiness: StructuredDecodeReadiness | None = None,
) -> Any:
    return run_generation_pipeline(
        request,
        renderer=renderer or FakeRenderer(),
        generator=FakeGenerator(outputs=outputs),
        backend=BackendIdentity(
            backend_identifier="fake-test-backend",
            backend_configuration_hash="f" * 64,
        ),
        structured_decode_readiness=readiness or _readiness(),
    )


class T12PipelineInputGatingTests(unittest.TestCase):
    def test_non_synthetic_rejected_before_rendering(self) -> None:
        renderer = FakeRenderer()
        result = _run(
            _pipeline_request(synthetic=False),
            outputs=[_json_output(_complete_semantic())],
            renderer=renderer,
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.REJECTED_NON_RETRYABLE.value)
        self.assertEqual(renderer.render_calls, 0)
        self.assertEqual(result.attempts_used, 0)

    def test_missing_eligibility_rejected(self) -> None:
        errors = validate_pipeline_request(
            GenerationPipelineRequest(
                caller_request_id="pred:1",
                synthetic=True,
                command="Go.",
                label_eligibility=None,  # type: ignore[arg-type]
                provenance_policy=default_synthetic_prediction_provenance_policy(),
                source_dataset="t12_synthetic",
                integrity_context=EMPTY_INTEGRITY,
            )
        )
        self.assertIn("label_eligibility is mandatory", errors)

    def test_missing_provenance_rejected(self) -> None:
        errors = validate_pipeline_request(
            GenerationPipelineRequest(
                caller_request_id="pred:1",
                synthetic=True,
                command="Go.",
                label_eligibility=LabelEligibility(routing=True),
                provenance_policy=None,  # type: ignore[arg-type]
                source_dataset="t12_synthetic",
                integrity_context=EMPTY_INTEGRITY,
            )
        )
        self.assertIn("provenance_policy is mandatory", errors)

    def test_blank_caller_id_rejected(self) -> None:
        result = _run(
            _pipeline_request(caller_request_id="  "),
            outputs=[_json_output(_complete_semantic())],
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.REJECTED_NON_RETRYABLE.value)
        self.assertEqual(result.attempts_used, 0)

    def test_blank_command_rejected(self) -> None:
        result = _run(
            _pipeline_request(command=""),
            outputs=[_json_output(_complete_semantic())],
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.REJECTED_NON_RETRYABLE.value)
        self.assertEqual(result.attempts_used, 0)

    def test_unverified_response_mode_zero_generator_calls(self) -> None:
        renderer = FakeRenderer(verified=False)
        generator = FakeGenerator(outputs=[_json_output(_complete_semantic())])
        result = run_generation_pipeline(
            _pipeline_request(),
            renderer=renderer,
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        self.assertEqual(result.attempts_used, 0)
        self.assertEqual(len(generator.calls), 0)
        self.assertEqual(
            result.failure_categories[0],
            FailureCategory.RESPONSE_MODE_UNVERIFIED.value,
        )

    def test_wrong_repository_zero_calls(self) -> None:
        renderer = FakeRenderer(repository="Wrong/Model")
        generator = FakeGenerator(outputs=[_json_output(_complete_semantic())])
        result = run_generation_pipeline(
            _pipeline_request(),
            renderer=renderer,
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        self.assertEqual(result.attempts_used, 0)
        self.assertEqual(len(generator.calls), 0)

    def test_wrong_revision_zero_calls(self) -> None:
        renderer = FakeRenderer(revision="0" * 40)
        generator = FakeGenerator(outputs=[_json_output(_complete_semantic())])
        result = run_generation_pipeline(
            _pipeline_request(),
            renderer=renderer,
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        self.assertEqual(result.attempts_used, 0)

    def test_missing_structured_decode_metadata_zero_calls(self) -> None:
        generator = FakeGenerator(outputs=[_json_output(_complete_semantic())])
        result = run_generation_pipeline(
            _pipeline_request(),
            renderer=FakeRenderer(),
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=None,
        )
        self.assertEqual(result.attempts_used, 0)
        self.assertIn(
            FailureCategory.STRUCTURED_DECODE_METADATA_ABSENT.value,
            result.failure_categories,
        )

    def test_schema_contract_mismatch_zero_calls(self) -> None:
        readiness = _readiness()
        bad_metadata = StructuredDecodeMetadata(
            contract_hash="0" * 64,
            schema_hash=readiness.metadata.schema_hash,
            sampling_params_module=readiness.metadata.sampling_params_module,
            sampling_params_class=readiness.metadata.sampling_params_class,
            structured_outputs_module=readiness.metadata.structured_outputs_module,
            structured_outputs_class=readiness.metadata.structured_outputs_class,
            structured_output_field_name=readiness.metadata.structured_output_field_name,
            schema_parameter_name=readiness.metadata.schema_parameter_name,
            required_vllm_version=readiness.metadata.required_vllm_version,
            detected_vllm_version=readiness.metadata.detected_vllm_version,
            completions_per_request=1,
            construction_status="constructed",
            response_mode_status=readiness.metadata.response_mode_status,
            engine_time_schema_compilation_status=readiness.metadata.engine_time_schema_compilation_status,
        )
        generator = FakeGenerator(outputs=[_json_output(_complete_semantic())])
        result = run_generation_pipeline(
            _pipeline_request(),
            renderer=FakeRenderer(),
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=StructuredDecodeReadiness(metadata=bad_metadata),
        )
        self.assertEqual(result.attempts_used, 0)
        self.assertIn(
            FailureCategory.STRUCTURED_DECODE_CONTRACT_MISMATCH.value,
            result.failure_categories,
        )

    def test_unconstrained_fallback_zero_calls(self) -> None:
        generator = FakeGenerator(outputs=[_json_output(_complete_semantic())])
        result = run_generation_pipeline(
            _pipeline_request(),
            renderer=FakeRenderer(),
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(unconstrained_fallback_indicated=True),
        )
        self.assertEqual(result.attempts_used, 0)
        self.assertIn(
            FailureCategory.UNCONSTRAINED_FALLBACK_INDICATED.value,
            result.failure_categories,
        )


class T12PipelineAttemptTests(unittest.TestCase):
    def test_valid_first_output_accepts_one_attempt(self) -> None:
        result = _run(
            _pipeline_request(),
            outputs=[_json_output(_complete_semantic())],
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.ACCEPTED.value)
        self.assertEqual(result.attempts_used, 1)
        self.assertEqual(result.accepted_raw_attempt_index, 0)
        self.assertIsNotNone(result.accepted_canonical_prediction)

    def test_invalid_json_then_valid_accepts_two_attempts(self) -> None:
        generator = FakeGenerator(
            outputs=["not json at all", _json_output(_complete_semantic())]
        )
        result = run_generation_pipeline(
            _pipeline_request(),
            renderer=FakeRenderer(),
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.ACCEPTED.value)
        self.assertEqual(result.attempts_used, 2)
        self.assertEqual(result.accepted_raw_attempt_index, 1)

    def test_schema_invalid_then_valid_accepts_two_attempts(self) -> None:
        bad = _complete_semantic()
        del bad["cpc"]
        result = _run(
            _pipeline_request(),
            outputs=[_json_output(bad), _json_output(_complete_semantic())],
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.ACCEPTED.value)
        self.assertEqual(result.attempts_used, 2)

    def test_canonical_assembly_failure_then_valid_accepts(self) -> None:
        bad = _complete_semantic(
            recommended_strategy=RouteLabel.CLARIFY.value,
            clarification_targets=[],
            clarification_question=None,
        )
        result = _run(
            _pipeline_request(
                label_eligibility=LabelEligibility(
                    routing=True,
                    ambiguity=True,
                    clarification_decision=True,
                ),
            ),
            outputs=[_json_output(bad), _json_output(_complete_semantic())],
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.ACCEPTED.value)
        self.assertEqual(result.attempts_used, 2)

    def test_unsupported_commitment_then_valid_accepts(self) -> None:
        bad_silent = _valid_silent_semantic()
        bad_silent["resolved_slots"] = [{"slot_name": "object", "value": "red vase"}]
        result = _run(
            _pipeline_request(
                command="Bring me the mug.",
                integrity_context=SYN003_INTEGRITY,
            ),
            outputs=[_json_output(bad_silent), _json_output(_valid_silent_semantic())],
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.ACCEPTED.value)
        self.assertEqual(result.attempts_used, 2)

    def test_three_invalid_attempts_rejected_after_attempts(self) -> None:
        result = _run(
            _pipeline_request(),
            outputs=["bad-1", "bad-2", "bad-3"],
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.REJECTED_AFTER_ATTEMPTS.value)
        self.assertTrue(result.attempts_exhausted)
        self.assertEqual(result.attempts_used, 3)

    def test_exactly_three_calls_maximum(self) -> None:
        generator = FakeGenerator(outputs=["bad"] * 5)
        run_generation_pipeline(
            _pipeline_request(),
            renderer=FakeRenderer(),
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        self.assertEqual(len(generator.calls), 3)

    def test_attempt_indexes_and_kinds(self) -> None:
        generator = FakeGenerator(outputs=["bad"] * 3)
        result = run_generation_pipeline(
            _pipeline_request(),
            renderer=FakeRenderer(),
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        indexes = [entry.attempt_index for entry in result.attempt_entries]
        kinds = [entry.attempt_kind for entry in result.attempt_entries]
        self.assertEqual(indexes, [0, 1, 2])
        self.assertEqual(kinds, list(ATTEMPT_KINDS))

    def test_every_raw_output_retained_exactly(self) -> None:
        outputs = ["RAW-ONE", "RAW-TWO", "RAW-THREE"]
        result = _run(_pipeline_request(), outputs=outputs)
        retained = [entry.raw_generated_text for entry in result.attempt_entries]
        self.assertEqual(retained, outputs)

    def test_local_repair_operations_retained_separately(self) -> None:
        fenced = f"```json\n{_json_output(_complete_semantic())}\n```"
        result = _run(_pipeline_request(), outputs=[fenced])
        entry = result.attempt_entries[0]
        self.assertIn("remove_markdown_json_fence", entry.local_repair_operations)
        self.assertIn("```", entry.raw_generated_text or "")

    def test_no_raw_output_replaced_by_repaired_text(self) -> None:
        fenced = f"```json\n{_json_output(_complete_semantic())}\n```"
        result = _run(_pipeline_request(), outputs=[fenced])
        entry = result.attempt_entries[0]
        self.assertNotEqual(entry.raw_generated_text, entry.extracted_json_text)

    def test_failure_reasons_retained(self) -> None:
        result = _run(_pipeline_request(), outputs=["not-json"])
        self.assertTrue(result.attempt_entries[0].failure_reasons)


class T12PipelineIdentityEvidenceTests(unittest.TestCase):
    def test_caller_id_remains_canonical(self) -> None:
        result = _run(
            _pipeline_request(caller_request_id="pred:canonical-42"),
            outputs=[_json_output(_complete_semantic())],
        )
        self.assertEqual(result.request_id, "pred:canonical-42")
        self.assertEqual(result.accepted_canonical_prediction["id"], "pred:canonical-42")

    def test_engine_id_recorded_not_in_canonical(self) -> None:
        generator = FakeGenerator(
            outputs=[_json_output(_complete_semantic())],
            engine_ids=["engine-diagnostic-99"],
        )
        result = run_generation_pipeline(
            _pipeline_request(),
            renderer=FakeRenderer(),
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        entry = result.attempt_entries[0]
        self.assertEqual(entry.engine_request_id, "engine-diagnostic-99")
        prediction = result.accepted_canonical_prediction or {}
        self.assertNotIn("engine_request_id", prediction)
        self.assertNotIn("engine_request_id", prediction.get("prediction_metadata", {}))

    def test_hashes_propagate(self) -> None:
        result = _run(_pipeline_request(), outputs=[_json_output(_complete_semantic())])
        entry = result.attempt_entries[0]
        self.assertEqual(len(entry.prompt_message_hash or ""), 64)
        self.assertEqual(len(entry.rendered_prompt_hash or ""), 64)
        self.assertEqual(len(result.semantic_schema_hash), 64)

    def test_mutable_generator_metadata_defensively_copied(self) -> None:
        metadata = {"nested": {"x": 1}}
        copied = defensive_copy_metadata(metadata)
        copied["nested"]["x"] = 99
        self.assertEqual(metadata["nested"]["x"], 1)

    def test_accepted_attempt_index_correct(self) -> None:
        result = _run(
            _pipeline_request(),
            outputs=["bad", _json_output(_complete_semantic())],
        )
        self.assertEqual(result.accepted_raw_attempt_index, 1)


class T12PipelineIntegrityTests(unittest.TestCase):
    def test_invalid_enum_never_accepted(self) -> None:
        bad = _complete_semantic(recommended_strategy="not_a_route")
        result = _run(_pipeline_request(), outputs=[_json_output(bad)] * 3)
        self.assertNotEqual(result.final_status, PipelineFinalStatus.ACCEPTED.value)

    def test_missing_nested_cpc_field_never_accepted(self) -> None:
        bad = _complete_semantic()
        cpc = dict(bad["cpc"])
        cpc["action"] = {"value": None}
        bad["cpc"] = cpc
        result = _run(_pipeline_request(), outputs=[_json_output(bad)] * 3)
        self.assertNotEqual(result.final_status, PipelineFinalStatus.ACCEPTED.value)

    def test_unknown_nested_field_never_accepted(self) -> None:
        bad = _complete_semantic()
        cpc = dict(bad["cpc"])
        cpc["action"] = {
            "value": None,
            "status": CPCSlotStatus.UNKNOWN.value,
            "extra": 1,
        }
        bad["cpc"] = cpc
        result = _run(_pipeline_request(), outputs=[_json_output(bad)] * 3)
        self.assertNotEqual(result.final_status, PipelineFinalStatus.ACCEPTED.value)

    def test_unsupported_silent_commitment_never_accepted(self) -> None:
        bad = _valid_silent_semantic()
        bad["resolved_slots"] = [{"slot_name": "object", "value": "red vase"}]
        result = _run(
            _pipeline_request(
                command="Bring me the mug.",
                integrity_context=SYN003_INTEGRITY,
            ),
            outputs=[_json_output(bad)] * 3,
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.REJECTED_AFTER_ATTEMPTS.value)

    def test_structural_and_semantic_correctness_separate_fields(self) -> None:
        result = _run(_pipeline_request(), outputs=[_json_output(_complete_semantic())])
        entry = result.attempt_entries[0]
        self.assertEqual(entry.structural_validity_status, "valid")
        self.assertEqual(entry.semantic_correctness_status, SEMANTIC_CORRECTNESS_NOT_EVALUATED)

    def test_no_t19_route_policy_in_module(self) -> None:
        source = (
            REPO_ROOT / "src" / "ambiguity_manager" / "model" / "generation_pipeline.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("route_policy_gate", source)
        self.assertNotIn("T19Router", source)

    def test_import_isolation(self) -> None:
        for name in list(sys.modules):
            if name.startswith(("torch", "vllm", "transformers")):
                del sys.modules[name]
        import ambiguity_manager.model.generation_pipeline  # noqa: F401

        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("vllm", sys.modules)
        self.assertNotIn("transformers", sys.modules)


class T12PipelineHardeningRedEvidence(unittest.TestCase):
    """Documents pre-hardening contract gaps now closed by D1C1 hardening."""

    def test_pre_hardening_integrity_optional_gap_documented(self) -> None:
        self.assertIn("integrity_context_mandatory", _contract_payload())
        self.assertTrue(_contract_payload()["integrity_context_mandatory"])

    def test_pre_hardening_generic_failure_gap_documented(self) -> None:
        self.assertTrue(_contract_payload()["unknown_generator_failures_non_retryable"])

    def test_pre_hardening_semantic_status_gap_documented(self) -> None:
        self.assertEqual(
            _contract_payload()["semantic_correctness_status_not_evaluated"],
            SEMANTIC_CORRECTNESS_NOT_EVALUATED,
        )


def _contract_payload() -> dict[str, Any]:
    return json.loads(
        (REPO_ROOT / "configs/model/t12_generation_pipeline_contract.json").read_text(
            encoding="utf-8"
        )
    )


class T12PipelineIntegrityContextTests(unittest.TestCase):
    def test_missing_integrity_context_rejects_before_rendering(self) -> None:
        renderer = FakeRenderer()
        generator = FakeGenerator(outputs=[_json_output(_complete_semantic())])
        request = _pipeline_request()
        request = GenerationPipelineRequest(
            caller_request_id=request.caller_request_id,
            synthetic=request.synthetic,
            command=request.command,
            label_eligibility=request.label_eligibility,
            provenance_policy=request.provenance_policy,
            source_dataset=request.source_dataset,
            integrity_context=None,  # type: ignore[arg-type]
        )
        result = run_generation_pipeline(
            request,
            renderer=renderer,
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.REJECTED_NON_RETRYABLE.value)
        self.assertEqual(renderer.render_calls, 0)
        self.assertEqual(len(generator.calls), 0)
        self.assertEqual(len(result.attempt_entries), 0)

    def test_none_integrity_context_validation(self) -> None:
        self.assertIn("integrity_context is mandatory", validate_integrity_context(None))

    def test_malformed_integrity_context_rejects_before_rendering(self) -> None:
        renderer = FakeRenderer()
        generator = FakeGenerator(outputs=[_json_output(_complete_semantic())])
        request = GenerationPipelineRequest(
            caller_request_id="pred:1",
            synthetic=True,
            command="Go.",
            label_eligibility=LabelEligibility(routing=True),
            provenance_policy=default_synthetic_prediction_provenance_policy(),
            source_dataset="t12_synthetic",
            integrity_context={"support_declarations": "bad"},  # type: ignore[arg-type]
        )
        result = run_generation_pipeline(
            request,
            renderer=renderer,
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.REJECTED_NON_RETRYABLE.value)
        self.assertEqual(renderer.render_calls, 0)
        self.assertEqual(len(generator.calls), 0)

    def test_empty_support_declarations_accepted_as_input(self) -> None:
        result = _run(
            _pipeline_request(integrity_context=EMPTY_INTEGRITY),
            outputs=[_json_output(_complete_semantic())],
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.ACCEPTED.value)

    def test_integrity_check_runs_with_empty_declarations(self) -> None:
        with patch(
            "ambiguity_manager.model.generation_pipeline.count_unsupported_commitments",
            return_value=0,
        ) as counter:
            result = _run(
                _pipeline_request(integrity_context=EMPTY_INTEGRITY),
                outputs=[_json_output(_complete_semantic())],
            )
        counter.assert_called_once()
        self.assertEqual(result.attempt_entries[0].unsupported_commitment_count, 0)

    def test_unsupported_silent_resolution_fails_with_empty_declarations(self) -> None:
        result = _run(
            _pipeline_request(
                command="Bring me the mug.",
                integrity_context=EMPTY_INTEGRITY,
            ),
            outputs=[_json_output(_valid_silent_semantic())],
        )
        self.assertNotEqual(result.final_status, PipelineFinalStatus.ACCEPTED.value)
        self.assertGreater(result.attempt_entries[0].unsupported_commitment_count or 0, 0)

    def test_supported_silent_resolution_passes_with_explicit_declarations(self) -> None:
        result = _run(
            _pipeline_request(
                command="Bring me the mug.",
                integrity_context=SYN003_INTEGRITY,
            ),
            outputs=[_json_output(_valid_silent_semantic())],
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.ACCEPTED.value)
        self.assertEqual(result.attempt_entries[0].unsupported_commitment_count, 0)

    def test_integrity_check_once_per_assembled_attempt(self) -> None:
        bad = _valid_silent_semantic()
        bad["resolved_slots"] = [{"slot_name": "object", "value": "red vase"}]
        with patch(
            "ambiguity_manager.model.generation_pipeline.count_unsupported_commitments",
            side_effect=[1, 0],
        ) as counter:
            result = _run(
                _pipeline_request(
                    command="Bring me the mug.",
                    integrity_context=SYN003_INTEGRITY,
                ),
                outputs=[_json_output(bad), _json_output(_valid_silent_semantic())],
            )
        self.assertEqual(counter.call_count, 2)
        self.assertEqual(result.final_status, PipelineFinalStatus.ACCEPTED.value)

    def test_regeneration_uses_same_integrity_context_hash(self) -> None:
        bad = _complete_semantic()
        del bad["cpc"]
        result = _run(
            _pipeline_request(integrity_context=SYN003_INTEGRITY),
            outputs=[_json_output(bad), _json_output(_complete_semantic())],
        )
        hashes = {entry.integrity_context_hash for entry in result.attempt_entries}
        self.assertEqual(len(hashes), 1)
        self.assertEqual(hashes.pop(), SYN003_INTEGRITY.hash())

    def test_support_declarations_not_mutated(self) -> None:
        raw = copy.deepcopy(SYN003_INTEGRITY_RAW)
        context = PipelineIntegrityContext.from_mapping(raw)
        _run(
            _pipeline_request(
                command="Bring me the mug.",
                integrity_context=context,
            ),
            outputs=[_json_output(_valid_silent_semantic())],
        )
        self.assertEqual(raw, SYN003_INTEGRITY_RAW)

    def test_mutable_support_metadata_defensively_copied(self) -> None:
        raw = copy.deepcopy(SYN003_INTEGRITY_RAW)
        context = PipelineIntegrityContext.from_mapping(raw)
        fixture = context.to_fixture_dict()
        fixture["support_declarations"]["supported_objects"].append("mutated")
        self.assertNotIn("mutated", context.to_fixture_dict()["support_declarations"]["supported_objects"])

    def test_integrity_count_in_assembled_attempt_entry(self) -> None:
        result = _run(_pipeline_request(), outputs=[_json_output(_complete_semantic())])
        entry = result.attempt_entries[0]
        self.assertIsNotNone(entry.unsupported_commitment_count)
        self.assertIsNotNone(entry.integrity_context_hash)


class T12PipelineGeneratorFailureTaxonomyTests(unittest.TestCase):
    def test_empty_returned_text_is_repairable(self) -> None:
        generator = FakeGenerator(outputs=["", _json_output(_complete_semantic())])
        result = run_generation_pipeline(
            _pipeline_request(),
            renderer=FakeRenderer(),
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        self.assertEqual(
            result.attempt_entries[0].failure_categories[0],
            FailureCategory.EMPTY_GENERATION_OUTPUT.value,
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.ACCEPTED.value)
        self.assertEqual(len(generator.calls), 2)

    def test_malformed_returned_text_is_repairable(self) -> None:
        generator = FakeGenerator(outputs=["not-json", _json_output(_complete_semantic())])
        result = run_generation_pipeline(
            _pipeline_request(),
            renderer=FakeRenderer(),
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.ACCEPTED.value)
        self.assertEqual(len(generator.calls), 2)

    def test_declared_repairable_output_failure_can_regenerate(self) -> None:
        transient = GeneratorOutput(
            raw_output="",
            generation_status="error",
            generation_error_type="transient_output_production_failure",
            generation_error_message="temporary output gap",
        )
        generator = FakeGenerator(
            outputs=[transient, _json_output(_complete_semantic())]
        )
        result = run_generation_pipeline(
            _pipeline_request(),
            renderer=FakeRenderer(),
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.ACCEPTED.value)
        self.assertEqual(len(generator.calls), 2)

    def test_dependency_failure_non_retryable(self) -> None:
        result = _run(
            _pipeline_request(),
            outputs=[
                GeneratorOutput(
                    raw_output="",
                    generation_status="error",
                    generation_error_type="backend_dependency_failure",
                    generation_error_message="dependency unavailable",
                )
            ],
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.REJECTED_NON_RETRYABLE.value)
        self.assertEqual(result.attempts_used, 1)

    def test_configuration_failure_non_retryable(self) -> None:
        result = _run(
            _pipeline_request(),
            outputs=[
                GeneratorOutput(
                    raw_output="",
                    generation_status="error",
                    generation_error_type="backend_configuration_failure",
                    generation_error_message="bad config",
                )
            ],
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.REJECTED_NON_RETRYABLE.value)

    def test_startup_failure_non_retryable(self) -> None:
        result = _run(
            _pipeline_request(),
            outputs=[
                GeneratorOutput(
                    raw_output="",
                    generation_status="error",
                    generation_error_type="backend_startup_failure",
                    generation_error_message="startup failed",
                )
            ],
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.REJECTED_NON_RETRYABLE.value)

    def test_unclassified_generator_error_non_retryable(self) -> None:
        result = _run(
            _pipeline_request(),
            outputs=[
                GeneratorOutput(
                    raw_output="",
                    generation_status="error",
                    generation_error_type="mystery_backend_fault",
                    generation_error_message="something broke",
                )
            ],
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.REJECTED_NON_RETRYABLE.value)
        self.assertEqual(
            result.failure_categories[0],
            FailureCategory.UNCLASSIFIED_GENERATOR_ERROR.value,
        )

    def test_unknown_exception_non_retryable_and_stops_immediately(self) -> None:
        generator = FakeGenerator(
            outputs=[_json_output(_complete_semantic())] * 3,
            raise_on_attempt={0: RuntimeError("synthetic boom")},
        )
        result = run_generation_pipeline(
            _pipeline_request(),
            renderer=FakeRenderer(),
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.REJECTED_NON_RETRYABLE.value)
        self.assertEqual(len(generator.calls), 0)
        self.assertEqual(result.attempts_used, 1)
        self.assertEqual(
            result.attempt_entries[0].generation_error_type,
            FailureCategory.UNKNOWN_EXCEPTION.value,
        )

    def test_unknown_exception_does_not_consume_three_attempts(self) -> None:
        generator = FakeGenerator(
            outputs=["bad"] * 3,
            raise_on_attempt={0: ValueError("fail")},
        )
        run_generation_pipeline(
            _pipeline_request(),
            renderer=FakeRenderer(),
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        self.assertEqual(len(generator.calls), 0)
        self.assertEqual(generator._index, 0)

    def test_exception_type_and_message_recorded(self) -> None:
        generator = FakeGenerator(raise_on_attempt={0: RuntimeError("synthetic boom")})
        result = run_generation_pipeline(
            _pipeline_request(),
            renderer=FakeRenderer(),
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        entry = result.attempt_entries[0]
        self.assertEqual(entry.generation_error_type, FailureCategory.UNKNOWN_EXCEPTION.value)
        self.assertIn("RuntimeError", entry.generation_error_message or "")
        self.assertNotIn("Traceback", entry.generation_error_message or "")

    def test_repairable_failures_still_max_three_calls(self) -> None:
        generator = FakeGenerator(outputs=["bad"] * 5)
        run_generation_pipeline(
            _pipeline_request(),
            renderer=FakeRenderer(),
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        self.assertEqual(len(generator.calls), 3)


class T12PipelineSelectedInterpretationRegressionTests(unittest.TestCase):
    def test_empty_supporting_evidence_rejected_and_regenerates(self) -> None:
        invalid = _complete_semantic(
            selected_interpretation={
                "frame_id": "frame_001",
                "supporting_evidence": [],
            },
        )
        generator = FakeGenerator(
            outputs=[_json_output(invalid), _json_output(_complete_semantic())]
        )
        result = run_generation_pipeline(
            _pipeline_request(),
            renderer=FakeRenderer(),
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.ACCEPTED.value)
        self.assertEqual(len(generator.calls), 2)
        self.assertEqual(
            result.attempt_entries[0].failure_categories[0],
            FailureCategory.SEMANTIC_SCHEMA_VALIDATION_FAILURE.value,
        )

    def test_empty_supporting_evidence_rejected_after_three_attempts(self) -> None:
        invalid = _complete_semantic(
            selected_interpretation={
                "frame_id": "frame_001",
                "supporting_evidence": [],
            },
        )
        generator = FakeGenerator(outputs=[_json_output(invalid)] * 3)
        result = run_generation_pipeline(
            _pipeline_request(),
            renderer=FakeRenderer(),
            generator=generator,
            backend=BackendIdentity("fake", "a" * 64),
            structured_decode_readiness=_readiness(),
        )
        self.assertEqual(result.final_status, PipelineFinalStatus.REJECTED_AFTER_ATTEMPTS.value)
        self.assertEqual(len(generator.calls), 3)


class T12PipelineSemanticStatusTests(unittest.TestCase):
    def test_structurally_accepted_has_not_evaluated_semantic_status(self) -> None:
        result = _run(_pipeline_request(), outputs=[_json_output(_complete_semantic())])
        entry = result.attempt_entries[0]
        self.assertEqual(entry.structural_validity_status, "valid")
        self.assertEqual(entry.semantic_correctness_status, SEMANTIC_CORRECTNESS_NOT_EVALUATED)

    def test_no_semantic_correctness_pass_recorded(self) -> None:
        result = _run(_pipeline_request(), outputs=[_json_output(_complete_semantic())])
        for entry in result.attempt_entries:
            self.assertNotEqual(entry.semantic_correctness_status, "passed")
            self.assertNotEqual(entry.semantic_correctness_status, "structural_only")

    def test_rejected_output_does_not_claim_semantic_evaluation(self) -> None:
        result = _run(_pipeline_request(), outputs=["bad"])
        self.assertEqual(
            result.attempt_entries[0].semantic_correctness_status,
            SEMANTIC_CORRECTNESS_NOT_EVALUATED,
        )

    def test_deterministic_serialization_preserves_semantic_status(self) -> None:
        result = _run(_pipeline_request(), outputs=[_json_output(_complete_semantic())])
        first = json.dumps(result.to_dict(), sort_keys=True)
        second = json.dumps(result.to_dict(), sort_keys=True)
        self.assertEqual(first, second)
        self.assertEqual(
            json.loads(first)["attempt_entries"][0]["semantic_correctness_status"],
            SEMANTIC_CORRECTNESS_NOT_EVALUATED,
        )

    def test_contract_records_not_evaluated_status(self) -> None:
        contract = _contract_payload()
        self.assertEqual(
            contract["semantic_correctness_status_not_evaluated"],
            SEMANTIC_CORRECTNESS_NOT_EVALUATED,
        )


if __name__ == "__main__":
    unittest.main()
