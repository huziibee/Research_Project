"""Tests for T12 Stage D1A prediction ownership and assembly contracts."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.model.prediction_contract import (
    DERIVATION_VERSION,
    DEFAULT_SYNTHETIC_PROVENANCE_POLICY_VERSION,
    FieldOwnership,
    MODEL_OUTPUT_REQUIRED_FIELDS,
    PredictionAssemblyError,
    PredictionProvenancePolicy,
    PredictionRequestContext,
    PredictionRuntimeMetadata,
    SemanticPayloadError,
    assemble_prediction_record,
    build_model_semantic_output_schema,
    canonical_prediction_schema_hash,
    default_synthetic_prediction_provenance_policy,
    extract_model_owned_semantic_fields,
    model_owned_prediction_fields,
    model_semantic_output_schema_bytes,
    model_semantic_output_schema_hash,
    prediction_field_ownership,
    runner_owned_prediction_fields,
    validate_ownership_contract,
    validate_semantic_payload,
)
from ambiguity_manager.model.semantic_schema_validator import POST_SCHEMA_VALIDATION_RULES
from ambiguity_manager.schema.v2.errors import SchemaValidationError
from ambiguity_manager.schema.v2.records import LabelEligibility
from ambiguity_manager.schema.v2.taxonomies import (
    AmbiguityType,
    AnnotationStatus,
    CapabilityStatus,
    CPCSlotStatus,
    LabelConfidence,
    RecordClass,
    RiskLevel,
    RouteLabel,
)
from ambiguity_manager.schema.v2.validation import validate_canonical_record_v2
from ambiguity_manager.schema.v2.version import SCHEMA_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKED_IN_SCHEMA = (
    REPO_ROOT / "configs" / "model" / "schema" / "t12_model_semantic_output.schema.json"
)


def _empty_cpc() -> dict:
    slot = {"value": None, "status": CPCSlotStatus.UNKNOWN.value}
    return {name: dict(slot) for name in (
        "action", "actor", "object", "object_attributes", "destination",
        "spatial_relation", "quantity", "time", "recipient", "tool",
        "conditions", "constraints", "negation",
    )}


def _complete_semantic(**overrides: object) -> dict:
    payload = {
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


def _request_context(**overrides: object) -> PredictionRequestContext:
    defaults = {
        "request_id": "pred:syn-test-001",
        "source_dataset": "t12_synthetic",
        "command": "Pick up the cup.",
        "label_eligibility": LabelEligibility(
            routing=True,
            ambiguity=True,
            clarification_decision=True,
        ),
    }
    defaults.update(overrides)
    return PredictionRequestContext(**defaults)


def _runtime_metadata(**overrides: object) -> PredictionRuntimeMetadata:
    defaults = {"model_id": "Qwen/Qwen3-8B"}
    defaults.update(overrides)
    return PredictionRuntimeMetadata(**defaults)


def _provenance_policy(**overrides: object) -> PredictionProvenancePolicy:
    defaults = default_synthetic_prediction_provenance_policy().__dict__
    defaults.update(overrides)
    return PredictionProvenancePolicy(**defaults)


class T12RedProbeSilentDefaultDefects(unittest.TestCase):
    """Red-phase probes documenting pre-hardening defects (now fixed)."""

    def test_empty_cpc_and_label_eligibility_rejected(self) -> None:
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload({"label_eligibility": {}, "cpc": {}})

    def test_empty_cpc_rejected(self) -> None:
        payload = _complete_semantic()
        payload["cpc"] = {}
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_missing_cpc_slot_rejected(self) -> None:
        payload = _complete_semantic()
        cpc = dict(payload["cpc"])
        del cpc["action"]
        payload["cpc"] = cpc
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_missing_cpc_slot_value_rejected(self) -> None:
        payload = _complete_semantic()
        cpc = dict(payload["cpc"])
        cpc["action"] = {"status": CPCSlotStatus.UNKNOWN.value}
        payload["cpc"] = cpc
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_missing_cpc_slot_status_rejected(self) -> None:
        payload = _complete_semantic()
        cpc = dict(payload["cpc"])
        cpc["action"] = {"value": None}
        payload["cpc"] = cpc
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_extra_cpc_slot_rejected(self) -> None:
        payload = _complete_semantic()
        cpc = dict(payload["cpc"])
        cpc["extra_slot"] = {"value": "x", "status": CPCSlotStatus.FILLED.value}
        payload["cpc"] = cpc
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_extra_cpc_slot_property_rejected(self) -> None:
        payload = _complete_semantic()
        cpc = dict(payload["cpc"])
        cpc["action"] = {
            "value": None,
            "status": CPCSlotStatus.UNKNOWN.value,
            "extra": 1,
        }
        payload["cpc"] = cpc
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_missing_evidence_source_rejected(self) -> None:
        payload = _complete_semantic(supporting_evidence=[{"span": "x"}])
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_extra_evidence_property_rejected(self) -> None:
        payload = _complete_semantic(
            supporting_evidence=[{"source": "cmd", "bad": 1}],
        )
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_model_label_eligibility_rejected(self) -> None:
        payload = _complete_semantic()
        payload["label_eligibility"] = LabelEligibility(routing=False).to_dict()
        with self.assertRaises(SemanticPayloadError) as ctx:
            validate_semantic_payload(payload)
        self.assertIn("label_eligibility", str(ctx.exception))


class T12PredictionOwnershipTests(unittest.TestCase):
    def test_every_prediction_field_classified(self) -> None:
        ownership = prediction_field_ownership()
        schema = build_model_semantic_output_schema()
        canonical_fields = set(schema.get("_canonical_prediction_fields", []))
        self.assertEqual(set(ownership), canonical_fields)

    def test_no_ownership_overlap(self) -> None:
        validate_ownership_contract()

    def test_label_eligibility_runner_owned(self) -> None:
        self.assertEqual(
            prediction_field_ownership()["label_eligibility"],
            FieldOwnership.RUNNER_OWNED,
        )
        self.assertNotIn("label_eligibility", build_model_semantic_output_schema()["properties"])

    def test_model_output_required_fields_complete(self) -> None:
        self.assertEqual(MODEL_OUTPUT_REQUIRED_FIELDS, model_owned_prediction_fields())
        schema = build_model_semantic_output_schema()
        self.assertEqual(set(schema["required"]), set(MODEL_OUTPUT_REQUIRED_FIELDS))

    def test_runner_owned_fields_exclude_model_schema(self) -> None:
        semantic = build_model_semantic_output_schema()
        overlap = runner_owned_prediction_fields() & set(semantic["properties"])
        self.assertEqual(overlap, set())

    def test_model_schema_retains_enum_constraints(self) -> None:
        semantic = build_model_semantic_output_schema()
        props = semantic["properties"]

        def _enum_values(prop: dict) -> set[str]:
            if "enum" in prop:
                return set(prop["enum"])
            if "oneOf" in prop:
                for branch in prop["oneOf"]:
                    if branch.get("type") != "null" and "enum" in branch:
                        return set(branch["enum"])
            raise AssertionError(f"no enum found in {prop!r}")

        self.assertEqual(
            _enum_values(props["recommended_strategy"]),
            {member.value for member in RouteLabel},
        )
        self.assertEqual(
            _enum_values(props["risk_level"]),
            {member.value for member in RiskLevel},
        )
        cpc_slot = props["cpc"]["properties"]["action"]["properties"]["status"]
        self.assertEqual(
            set(cpc_slot["enum"]),
            {member.value for member in CPCSlotStatus},
        )

    def test_schema_contains_standard_route_conditionals(self) -> None:
        schema = build_model_semantic_output_schema()
        self.assertIn("allOf", schema)
        self.assertNotIn("route_conditional_requirements", schema)
        all_of_text = json.dumps(schema["allOf"])
        for route in (
            RouteLabel.SILENTLY_RESOLVE.value,
            RouteLabel.CLARIFY.value,
            RouteLabel.FACE_PRESERVING_REJECTION.value,
            RouteLabel.MULTI_STEP.value,
        ):
            self.assertIn(route, all_of_text)

    def test_post_schema_rules_documented(self) -> None:
        schema = build_model_semantic_output_schema()
        self.assertEqual(schema["_post_schema_validation_rules"], list(POST_SCHEMA_VALIDATION_RULES))

    def test_canonical_schema_hash_stable(self) -> None:
        first = canonical_prediction_schema_hash()
        second = canonical_prediction_schema_hash()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_semantic_schema_hash_stable(self) -> None:
        first = model_semantic_output_schema_hash()
        second = model_semantic_output_schema_hash()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_checked_in_schema_matches_generated(self) -> None:
        self.assertTrue(CHECKED_IN_SCHEMA.is_file(), "checked-in semantic schema missing")
        checked = CHECKED_IN_SCHEMA.read_bytes()
        generated = model_semantic_output_schema_bytes()
        self.assertEqual(checked, generated)

    def test_derivation_version_recorded(self) -> None:
        semantic = build_model_semantic_output_schema()
        self.assertEqual(semantic["derivation_version"], DERIVATION_VERSION)


class T12SemanticPayloadValidationTests(unittest.TestCase):
    def test_unknown_model_fields_fail(self) -> None:
        payload = _complete_semantic(extra_field="not_allowed")
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_runner_owned_fields_in_payload_fail(self) -> None:
        payload = _complete_semantic(id="pred:override", command="other")
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_omitted_ambiguity_present_fails(self) -> None:
        payload = _complete_semantic()
        del payload["ambiguity_present"]
        with self.assertRaises(SemanticPayloadError) as ctx:
            validate_semantic_payload(payload)
        self.assertIn("ambiguity_present", str(ctx.exception))

    def test_omitted_risk_level_fails_even_when_null_allowed(self) -> None:
        payload = _complete_semantic()
        del payload["risk_level"]
        with self.assertRaises(SemanticPayloadError) as ctx:
            validate_semantic_payload(payload)
        self.assertIn("risk_level", str(ctx.exception))

    def test_omitted_recommended_strategy_fails(self) -> None:
        payload = _complete_semantic()
        del payload["recommended_strategy"]
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)


class T12RouteConditionalSchemaTests(unittest.TestCase):
    def test_silently_resolve_missing_components_fail(self) -> None:
        payload = _complete_semantic(
            recommended_strategy=RouteLabel.SILENTLY_RESOLVE.value,
            resolved_slots=[],
            resolution_method=None,
            resolution_evidence=[],
        )
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_clarify_missing_target_or_question_fail(self) -> None:
        payload = _complete_semantic(
            recommended_strategy=RouteLabel.CLARIFY.value,
            clarification_targets=[],
            clarification_question=None,
        )
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_rejection_missing_reason_fails(self) -> None:
        payload = _complete_semantic(
            recommended_strategy=RouteLabel.FACE_PRESERVING_REJECTION.value,
            rejection_reason=None,
        )
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_multi_step_requires_two_or_more_steps(self) -> None:
        payload = _complete_semantic(
            recommended_strategy=RouteLabel.MULTI_STEP.value,
            strategy_sequence=[RouteLabel.EXECUTE.value],
        )
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_non_multi_step_requires_empty_sequence(self) -> None:
        payload = _complete_semantic(
            recommended_strategy=RouteLabel.EXECUTE.value,
            strategy_sequence=[RouteLabel.CLARIFY.value],
        )
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)


class T12EligibilityOwnershipTests(unittest.TestCase):
    def test_runner_eligibility_mandatory_for_assembly(self) -> None:
        with self.assertRaises(TypeError):
            PredictionRequestContext(
                request_id="pred:1",
                source_dataset="t12",
                command="Go.",
            )

    def test_runner_eligibility_preserved(self) -> None:
        eligibility = LabelEligibility(routing=True, risk=True, capability=True)
        record = assemble_prediction_record(
            _request_context(label_eligibility=eligibility),
            _complete_semantic(risk_level=RiskLevel.LOW.value, capability_status=CapabilityStatus.CAPABLE.value),
            _runtime_metadata(),
            _provenance_policy(),
        )
        self.assertEqual(record["label_eligibility"], eligibility.to_dict())

    def test_model_cannot_suppress_risk_via_false_eligibility(self) -> None:
        payload = _complete_semantic(label_eligibility={"routing": False, "risk": False})
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_risk_eligibility_requires_non_null_risk_level(self) -> None:
        with self.assertRaises(PredictionAssemblyError):
            assemble_prediction_record(
                _request_context(
                    label_eligibility=LabelEligibility(routing=True, risk=True),
                ),
                _complete_semantic(risk_level=None),
                _runtime_metadata(),
                _provenance_policy(),
            )

    def test_capability_eligibility_requires_non_null_capability_status(self) -> None:
        with self.assertRaises(PredictionAssemblyError):
            assemble_prediction_record(
                _request_context(
                    label_eligibility=LabelEligibility(routing=True, capability=True),
                ),
                _complete_semantic(capability_status=None),
                _runtime_metadata(),
                _provenance_policy(),
            )


class T12ProvenancePolicyTests(unittest.TestCase):
    def test_provenance_values_from_explicit_runner_policy(self) -> None:
        policy = PredictionProvenancePolicy(
            policy_version="test-provenance-1.0.0",
            annotation_status=AnnotationStatus.WEAK_MAPPED,
            label_confidence=LabelConfidence.WEAK_DERIVED,
            explanation="test placeholder",
        )
        record = assemble_prediction_record(
            _request_context(),
            _complete_semantic(),
            _runtime_metadata(),
            policy,
        )
        self.assertEqual(record["annotation_status"], AnnotationStatus.WEAK_MAPPED.value)
        self.assertEqual(record["label_confidence"], LabelConfidence.WEAK_DERIVED.value)

    def test_model_cannot_set_provenance_fields(self) -> None:
        payload = _complete_semantic(annotation_status="manually_annotated")
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_default_synthetic_provenance_is_versioned(self) -> None:
        policy = default_synthetic_prediction_provenance_policy()
        self.assertEqual(policy.policy_version, DEFAULT_SYNTHETIC_PROVENANCE_POLICY_VERSION)
        self.assertIn("placeholder", policy.explanation.lower())


class T12PredictionAssemblerTests(unittest.TestCase):
    def test_caller_id_preserved(self) -> None:
        record = assemble_prediction_record(
            _request_context(request_id="pred:canonical-id"),
            _complete_semantic(),
            _runtime_metadata(),
            _provenance_policy(),
        )
        self.assertEqual(record["id"], "pred:canonical-id")

    def test_command_preserved_byte_for_byte(self) -> None:
        command = "Move that thing over there after a while."
        record = assemble_prediction_record(
            _request_context(command=command),
            _complete_semantic(),
            _runtime_metadata(),
            _provenance_policy(),
        )
        self.assertEqual(record["command"], command)

    def test_schema_version_runner_supplied(self) -> None:
        with self.assertRaises(SemanticPayloadError):
            assemble_prediction_record(
                _request_context(),
                _complete_semantic(schema_version="9.9.9"),
                _runtime_metadata(),
                _provenance_policy(),
            )
        record = assemble_prediction_record(
            _request_context(),
            _complete_semantic(),
            _runtime_metadata(),
            _provenance_policy(),
        )
        self.assertEqual(record["schema_version"], SCHEMA_VERSION)

    def test_record_class_runner_supplied(self) -> None:
        with self.assertRaises(SemanticPayloadError):
            assemble_prediction_record(
                _request_context(),
                _complete_semantic(record_class="adjudicated_gold"),
                _runtime_metadata(),
                _provenance_policy(),
            )
        record = assemble_prediction_record(
            _request_context(),
            _complete_semantic(),
            _runtime_metadata(),
            _provenance_policy(),
        )
        self.assertEqual(record["record_class"], RecordClass.PREDICTION.value)

    def test_conflicting_runner_model_values_fail(self) -> None:
        with self.assertRaises(SemanticPayloadError):
            assemble_prediction_record(
                _request_context(source_dataset="t12_synthetic"),
                _complete_semantic(source_dataset="other_dataset"),
                _runtime_metadata(),
                _provenance_policy(),
            )

    def test_valid_semantic_payload_assembles_schema_valid(self) -> None:
        record = assemble_prediction_record(
            _request_context(),
            _complete_semantic(),
            _runtime_metadata(prompt_hash="abc123"),
            _provenance_policy(),
        )
        validated = validate_canonical_record_v2(record)
        self.assertEqual(validated.record_class, RecordClass.PREDICTION)
        self.assertEqual(validated.annotation_status, AnnotationStatus.WEAK_MAPPED)
        self.assertEqual(validated.label_confidence, LabelConfidence.WEAK_DERIVED)

    def test_invalid_enum_fails(self) -> None:
        with self.assertRaises(SemanticPayloadError):
            assemble_prediction_record(
                _request_context(),
                _complete_semantic(recommended_strategy="not_a_route"),
                _runtime_metadata(),
                _provenance_policy(),
            )

    def test_invalid_cpc_status_fails(self) -> None:
        semantic = _complete_semantic()
        semantic["cpc"]["action"]["status"] = "not_a_status"
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(semantic)

    def test_malformed_cpc_type_fails(self) -> None:
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(_complete_semantic(cpc="not-an-object"))

    def test_invalid_speech_act_outside_intent_labels_fails(self) -> None:
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(_complete_semantic(speech_act="request"))

    def test_semantic_round_trip_preserves_model_fields(self) -> None:
        payload = _complete_semantic(
            speech_act="directive_command",
            intent_summary="pick up object",
        )
        record = assemble_prediction_record(
            _request_context(),
            payload,
            _runtime_metadata(),
            _provenance_policy(),
        )
        # Round-trip may materialise approved optional nulls on the assembled side;
        # equality holds after the same comparison-only normalisation.
        from ambiguity_manager.model.prediction_contract import (
            _materialize_optional_canonical_nulls_for_comparison,
        )

        self.assertEqual(
            _materialize_optional_canonical_nulls_for_comparison(
                extract_model_owned_semantic_fields(record)
            ),
            _materialize_optional_canonical_nulls_for_comparison(payload),
        )

    def test_parser_default_insertion_detected(self) -> None:
        payload = _complete_semantic()
        del payload["compound_ambiguity"]
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)

    def test_assembler_never_returns_invalid_record(self) -> None:
        bad_cases = [
            _complete_semantic(recommended_strategy="not_a_route"),
            _complete_semantic(
                recommended_strategy=RouteLabel.CLARIFY.value,
                clarification_targets=["object"],
            ),
        ]
        for semantic in bad_cases:
            with self.subTest(semantic=semantic):
                with self.assertRaises(Exception):
                    record = assemble_prediction_record(
                        _request_context(),
                        semantic,
                        _runtime_metadata(),
                        _provenance_policy(),
                    )
                    validate_canonical_record_v2(record)


def _job3974_style_semantic(*, omit_text: bool, omit_safety: bool, omit_note: bool) -> dict:
    """Minimal execute payload matching job-3974 optional-omission pattern."""
    candidate: dict = {
        "frame_id": "frame_001",
        "confidence": 1.0,
        "cpc": _empty_cpc(),
    }
    if not omit_text:
        candidate["text"] = None
    if not omit_safety:
        candidate["safety_status"] = None
    evidence_item: dict = {
        "source": "original command",
        "span": "Turn on the desk lamp.",
    }
    if not omit_note:
        evidence_item["note"] = None
    return _complete_semantic(
        intent_summary="Turn on the desk lamp.",
        candidate_interpretations=[candidate],
        selected_interpretation={
            "frame_id": "frame_001",
            "supporting_evidence": [dict(evidence_item)],
        },
        supporting_evidence=[dict(evidence_item)],
        recommended_strategy=RouteLabel.EXECUTE.value,
    )


class T12OptionalNullRoundTripTests(unittest.TestCase):
    def test_omitted_candidate_text_equals_canonical_null(self) -> None:
        payload = _job3974_style_semantic(omit_text=True, omit_safety=False, omit_note=False)
        validate_semantic_payload(payload)
        record = assemble_prediction_record(
            _request_context(),
            payload,
            _runtime_metadata(),
            _provenance_policy(),
        )
        extracted = extract_model_owned_semantic_fields(record)
        self.assertIsNone(extracted["candidate_interpretations"][0]["text"])
        self.assertNotIn("text", payload["candidate_interpretations"][0])

    def test_omitted_candidate_safety_status_equals_canonical_null(self) -> None:
        payload = _job3974_style_semantic(omit_text=False, omit_safety=True, omit_note=False)
        validate_semantic_payload(payload)
        record = assemble_prediction_record(
            _request_context(),
            payload,
            _runtime_metadata(),
            _provenance_policy(),
        )
        extracted = extract_model_owned_semantic_fields(record)
        self.assertIsNone(extracted["candidate_interpretations"][0]["safety_status"])
        self.assertNotIn("safety_status", payload["candidate_interpretations"][0])

    def test_omitted_supporting_evidence_note_equals_canonical_null(self) -> None:
        payload = _job3974_style_semantic(omit_text=False, omit_safety=False, omit_note=True)
        validate_semantic_payload(payload)
        record = assemble_prediction_record(
            _request_context(),
            payload,
            _runtime_metadata(),
            _provenance_policy(),
        )
        extracted = extract_model_owned_semantic_fields(record)
        self.assertIsNone(extracted["selected_interpretation"]["supporting_evidence"][0]["note"])
        self.assertIsNone(extracted["supporting_evidence"][0]["note"])
        self.assertNotIn("note", payload["selected_interpretation"]["supporting_evidence"][0])

    def test_combined_job3974_optional_omissions_assemble(self) -> None:
        payload = _job3974_style_semantic(omit_text=True, omit_safety=True, omit_note=True)
        snapshot = json.loads(json.dumps(payload))
        validate_semantic_payload(payload)
        record = assemble_prediction_record(
            _request_context(),
            payload,
            _runtime_metadata(),
            _provenance_policy(),
        )
        self.assertEqual(payload, snapshot)
        validate_canonical_record_v2(record)
        extracted = extract_model_owned_semantic_fields(record)
        self.assertIsNone(extracted["candidate_interpretations"][0]["text"])
        self.assertIsNone(extracted["candidate_interpretations"][0]["safety_status"])
        self.assertIsNone(extracted["selected_interpretation"]["supporting_evidence"][0]["note"])

    def test_normalisation_is_comparison_only_and_deterministic(self) -> None:
        from ambiguity_manager.model.prediction_contract import (
            _materialize_optional_canonical_nulls_for_comparison,
        )

        payload = _job3974_style_semantic(omit_text=True, omit_safety=True, omit_note=True)
        first = _materialize_optional_canonical_nulls_for_comparison(payload)
        second = _materialize_optional_canonical_nulls_for_comparison(payload)
        self.assertEqual(first, second)
        self.assertNotIn("text", payload["candidate_interpretations"][0])
        self.assertNotIn("safety_status", payload["candidate_interpretations"][0])
        self.assertNotIn("note", payload["supporting_evidence"][0])
        self.assertIsNone(first["candidate_interpretations"][0]["text"])
        self.assertIsNone(first["candidate_interpretations"][0]["safety_status"])
        self.assertIsNone(first["supporting_evidence"][0]["note"])

    def test_emitted_text_versus_canonical_null_fails(self) -> None:
        from ambiguity_manager.model.prediction_contract import (
            _assert_semantic_round_trip,
        )

        original = _job3974_style_semantic(omit_text=False, omit_safety=True, omit_note=True)
        original["candidate_interpretations"][0]["text"] = "abc"
        assembled = _job3974_style_semantic(omit_text=False, omit_safety=True, omit_note=True)
        assembled["candidate_interpretations"][0]["text"] = None
        with self.assertRaises(PredictionAssemblyError):
            _assert_semantic_round_trip(original, assembled)

    def test_safety_status_value_mutation_fails(self) -> None:
        from ambiguity_manager.model.prediction_contract import (
            _assert_semantic_round_trip,
        )
        from ambiguity_manager.schema.v2.taxonomies import SafetyStatus

        original = _job3974_style_semantic(omit_text=True, omit_safety=False, omit_note=True)
        original["candidate_interpretations"][0]["safety_status"] = SafetyStatus.SAFE.value
        assembled = _job3974_style_semantic(omit_text=True, omit_safety=False, omit_note=True)
        assembled["candidate_interpretations"][0]["safety_status"] = SafetyStatus.UNSAFE.value
        with self.assertRaises(PredictionAssemblyError):
            _assert_semantic_round_trip(original, assembled)

    def test_supporting_evidence_source_mutation_fails(self) -> None:
        from ambiguity_manager.model.prediction_contract import (
            _assert_semantic_round_trip,
        )

        original = _job3974_style_semantic(omit_text=True, omit_safety=True, omit_note=True)
        assembled = _job3974_style_semantic(omit_text=True, omit_safety=True, omit_note=True)
        assembled["selected_interpretation"]["supporting_evidence"][0]["source"] = "scene_context"
        assembled["supporting_evidence"][0]["source"] = "scene_context"
        with self.assertRaises(PredictionAssemblyError):
            _assert_semantic_round_trip(original, assembled)

    def test_evidence_item_removal_fails(self) -> None:
        from ambiguity_manager.model.prediction_contract import (
            _assert_semantic_round_trip,
        )

        original = _job3974_style_semantic(omit_text=True, omit_safety=True, omit_note=True)
        original["selected_interpretation"]["supporting_evidence"].append(
            {"source": "scene_context", "span": "desk"}
        )
        original["supporting_evidence"].append({"source": "scene_context", "span": "desk"})
        assembled = _job3974_style_semantic(omit_text=True, omit_safety=True, omit_note=True)
        with self.assertRaises(PredictionAssemblyError):
            _assert_semantic_round_trip(original, assembled)

    def test_candidate_order_change_fails(self) -> None:
        from ambiguity_manager.model.prediction_contract import (
            _assert_semantic_round_trip,
        )

        first = {
            "frame_id": "frame_001",
            "confidence": 1.0,
            "cpc": _empty_cpc(),
        }
        second = {
            "frame_id": "frame_002",
            "confidence": 0.5,
            "cpc": _empty_cpc(),
        }
        evidence = [{"source": "original command", "span": "lamp"}]
        original = _complete_semantic(
            candidate_interpretations=[dict(first), dict(second)],
            selected_interpretation={"frame_id": "frame_001", "supporting_evidence": evidence},
            supporting_evidence=evidence,
        )
        assembled = _complete_semantic(
            candidate_interpretations=[dict(second), dict(first)],
            selected_interpretation={"frame_id": "frame_001", "supporting_evidence": evidence},
            supporting_evidence=evidence,
        )
        with self.assertRaises(PredictionAssemblyError):
            _assert_semantic_round_trip(original, assembled)

    def test_arbitrary_missing_null_field_remains_unequal(self) -> None:
        from ambiguity_manager.model.prediction_contract import (
            _assert_semantic_round_trip,
            _materialize_optional_canonical_nulls_for_comparison,
        )

        original = _complete_semantic(intent_summary="pick up object")
        # intent_summary is model-owned but not an approved optional-null path
        assembled = _complete_semantic()
        assembled["intent_summary"] = None
        del original["intent_summary"]
        left = _materialize_optional_canonical_nulls_for_comparison(original)
        right = _materialize_optional_canonical_nulls_for_comparison(assembled)
        self.assertNotEqual(left, right)
        with self.assertRaises(PredictionAssemblyError):
            _assert_semantic_round_trip(original, assembled)

    def test_empty_selected_supporting_evidence_remains_schema_invalid(self) -> None:
        payload = _complete_semantic(
            selected_interpretation={"frame_id": "frame_001", "supporting_evidence": []},
            supporting_evidence=[{"source": "command", "span": "cup"}],
            candidate_interpretations=[
                {"frame_id": "frame_001", "confidence": 1.0, "cpc": _empty_cpc()}
            ],
        )
        with self.assertRaises(SemanticPayloadError):
            validate_semantic_payload(payload)
        with self.assertRaises(SemanticPayloadError):
            assemble_prediction_record(
                _request_context(),
                payload,
                _runtime_metadata(),
                _provenance_policy(),
            )


class T12JsonSchemaDependencyTests(unittest.TestCase):
    def test_jsonschema_import_available(self) -> None:
        import jsonschema  # noqa: F401

    def test_prediction_contract_declares_jsonschema_dependency(self) -> None:
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("jsonschema", pyproject)


if __name__ == "__main__":
    unittest.main()
