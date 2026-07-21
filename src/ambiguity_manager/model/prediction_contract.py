"""Schema-v2 prediction ownership, semantic schema, and assembly contracts."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.schema.v2.errors import SchemaValidationError
from ambiguity_manager.schema.v2.json_schema import (
    _evidence_ref_schema,
    build_prediction_json_schema,
    prediction_json_schema_bytes,
)
from ambiguity_manager.schema.v2.records import LabelEligibility, canonical_record_v2_from_dict
from ambiguity_manager.schema.v2.taxonomies import (
    AnnotationStatus,
    LabelConfidence,
    RecordClass,
    RouteLabel,
    SplitStatus,
)
from ambiguity_manager.schema.v2.validation import validate_canonical_record_v2
from ambiguity_manager.schema.v2.version import SCHEMA_VERSION

DERIVATION_VERSION = "t12-d1a-1.1.0"
SEMANTIC_SCHEMA_FILENAME = "t12_model_semantic_output.schema.json"
DEFAULT_SYNTHETIC_PROVENANCE_POLICY_VERSION = "t12-d1a-synthetic-placeholder-1.0.0"

ACCEPTANCE_RULE_IDS: tuple[str, ...] = (
    "canonical_schema_validation",
    "schema_route_conditional_checks",
    "unsupported_silent_commitment_checks",
    "invalid_enum_rejection",
    "malformed_nested_structure_rejection",
)


class FieldOwnership(StrEnum):
    RUNNER_OWNED = "runner_owned"
    MODEL_OWNED = "model_owned"
    ASSEMBLED_OR_DERIVED = "assembled_or_derived"


PREDICTION_FIELD_OWNERSHIP: dict[str, FieldOwnership] = {
    "schema_version": FieldOwnership.RUNNER_OWNED,
    "id": FieldOwnership.RUNNER_OWNED,
    "record_class": FieldOwnership.RUNNER_OWNED,
    "source_dataset": FieldOwnership.RUNNER_OWNED,
    "source_id": FieldOwnership.RUNNER_OWNED,
    "original_split": FieldOwnership.RUNNER_OWNED,
    "group_id": FieldOwnership.RUNNER_OWNED,
    "split_status": FieldOwnership.RUNNER_OWNED,
    "command": FieldOwnership.RUNNER_OWNED,
    "scene_context": FieldOwnership.RUNNER_OWNED,
    "dialogue_history": FieldOwnership.RUNNER_OWNED,
    "capability_context": FieldOwnership.RUNNER_OWNED,
    "annotation_status": FieldOwnership.RUNNER_OWNED,
    "label_confidence": FieldOwnership.RUNNER_OWNED,
    "migration_version": FieldOwnership.RUNNER_OWNED,
    "migrated_from_schema_version": FieldOwnership.RUNNER_OWNED,
    "v1_legacy": FieldOwnership.RUNNER_OWNED,
    "prediction_metadata": FieldOwnership.ASSEMBLED_OR_DERIVED,
    "mapping_version": FieldOwnership.RUNNER_OWNED,
    "source_license": FieldOwnership.RUNNER_OWNED,
    "mapping_notes": FieldOwnership.RUNNER_OWNED,
    "source_metadata": FieldOwnership.RUNNER_OWNED,
    "label_eligibility": FieldOwnership.RUNNER_OWNED,
    "cpc": FieldOwnership.MODEL_OWNED,
    "speech_act": FieldOwnership.MODEL_OWNED,
    "intent_summary": FieldOwnership.MODEL_OWNED,
    "candidate_interpretations": FieldOwnership.MODEL_OWNED,
    "selected_interpretation": FieldOwnership.MODEL_OWNED,
    "unresolved_slots": FieldOwnership.MODEL_OWNED,
    "supporting_evidence": FieldOwnership.MODEL_OWNED,
    "ambiguity_present": FieldOwnership.MODEL_OWNED,
    "ambiguity_types": FieldOwnership.MODEL_OWNED,
    "primary_ambiguity_type": FieldOwnership.MODEL_OWNED,
    "compound_ambiguity": FieldOwnership.MODEL_OWNED,
    "compound_ambiguity_count": FieldOwnership.MODEL_OWNED,
    "risk_relevant": FieldOwnership.MODEL_OWNED,
    "risk_level": FieldOwnership.MODEL_OWNED,
    "capability_status": FieldOwnership.MODEL_OWNED,
    "recommended_strategy": FieldOwnership.MODEL_OWNED,
    "strategy_sequence": FieldOwnership.MODEL_OWNED,
    "clarification_question": FieldOwnership.MODEL_OWNED,
    "clarification_subtype": FieldOwnership.MODEL_OWNED,
    "clarification_targets": FieldOwnership.MODEL_OWNED,
    "rejection_reason": FieldOwnership.MODEL_OWNED,
    "resolved_slots": FieldOwnership.MODEL_OWNED,
    "resolution_method": FieldOwnership.MODEL_OWNED,
    "resolution_evidence": FieldOwnership.MODEL_OWNED,
    "context_sampling_uncertainty": FieldOwnership.MODEL_OWNED,
}

MODEL_OUTPUT_REQUIRED_FIELDS: frozenset[str] = frozenset(
    name
    for name, owner in PREDICTION_FIELD_OWNERSHIP.items()
    if owner == FieldOwnership.MODEL_OWNED
)


class PredictionContractError(Exception):
    """Base error for prediction contract operations."""


class SemanticPayloadError(PredictionContractError):
    """Raised when a model semantic payload violates the D1A contract."""


class PredictionAssemblyError(PredictionContractError):
    """Raised when a full prediction record cannot be assembled safely."""


@dataclass(frozen=True)
class PredictionProvenancePolicy:
    """Explicit runner policy for synthetic prediction provenance placeholders."""

    policy_version: str
    annotation_status: AnnotationStatus
    label_confidence: LabelConfidence
    explanation: str
    evidence_identifier: str | None = None


@dataclass(frozen=True)
class PredictionRequestContext:
    request_id: str
    source_dataset: str
    command: str
    label_eligibility: LabelEligibility
    scene_context: str | None = None
    dialogue_history: list[str] = field(default_factory=list)
    capability_context: str | None = None
    source_id: str | None = None
    original_split: str | None = None
    group_id: str | None = None
    split_status: SplitStatus = SplitStatus.UNSPLIT
    mapping_version: str | None = None
    source_license: str | None = None
    mapping_notes: str | None = None
    source_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class PredictionRuntimeMetadata:
    model_id: str
    prompt_hash: str | None = None
    generation_seed: int | None = None
    raw_model_output: str | None = None


def default_synthetic_prediction_provenance_policy() -> PredictionProvenancePolicy:
    """Schema-compatible synthetic placeholders; not human annotation provenance."""
    return PredictionProvenancePolicy(
        policy_version=DEFAULT_SYNTHETIC_PROVENANCE_POLICY_VERSION,
        annotation_status=AnnotationStatus.WEAK_MAPPED,
        label_confidence=LabelConfidence.WEAK_DERIVED,
        explanation=(
            "Schema-compatible synthetic-prediction placeholder values. "
            "These are not human annotation provenance and must be replaced "
            "before official experiments."
        ),
        evidence_identifier="configs/model/evidence/t12_stage_d1a_contract.json",
    )


def prediction_field_ownership() -> dict[str, FieldOwnership]:
    return dict(PREDICTION_FIELD_OWNERSHIP)


def runner_owned_prediction_fields() -> frozenset[str]:
    return frozenset(
        name
        for name, owner in PREDICTION_FIELD_OWNERSHIP.items()
        if owner in (FieldOwnership.RUNNER_OWNED, FieldOwnership.ASSEMBLED_OR_DERIVED)
    )


def model_owned_prediction_fields() -> frozenset[str]:
    return frozenset(
        name
        for name, owner in PREDICTION_FIELD_OWNERSHIP.items()
        if owner == FieldOwnership.MODEL_OWNED
    )


def validate_ownership_contract() -> None:
    canonical = build_prediction_json_schema()
    canonical_fields = set(canonical["properties"])
    owned_fields = set(PREDICTION_FIELD_OWNERSHIP)
    if canonical_fields != owned_fields:
        missing = sorted(canonical_fields - owned_fields)
        extra = sorted(owned_fields - canonical_fields)
        raise PredictionContractError(
            f"ownership contract mismatch; missing={missing!r} extra={extra!r}"
        )
    required = set(canonical["required"])
    if not required.issubset(owned_fields):
        raise PredictionContractError(
            f"required fields missing from ownership contract: {sorted(required - owned_fields)!r}"
        )
    grouped: dict[str, list[str]] = {}
    for field_name, owner in PREDICTION_FIELD_OWNERSHIP.items():
        grouped.setdefault(owner.value, []).append(field_name)
    if len(PREDICTION_FIELD_OWNERSHIP) != sum(len(items) for items in grouped.values()):
        raise PredictionContractError("ownership overlap detected")
    if "label_eligibility" in model_owned_prediction_fields():
        raise PredictionContractError("label_eligibility must not be model-owned")
    if MODEL_OUTPUT_REQUIRED_FIELDS != model_owned_prediction_fields():
        raise PredictionContractError("MODEL_OUTPUT_REQUIRED_FIELDS mismatch")


def _route_conditional_allof() -> list[dict[str, Any]]:
    evidence_item = _evidence_ref_schema()
    resolved_slot_item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "slot_name": {"type": "string", "minLength": 1},
            "value": {"type": "string", "minLength": 1},
        },
        "required": ["slot_name", "value"],
    }
    return [
        {
            "if": {
                "properties": {
                    "recommended_strategy": {"const": RouteLabel.SILENTLY_RESOLVE.value},
                },
                "required": ["recommended_strategy"],
            },
            "then": {
                "properties": {
                    "resolved_slots": {"type": "array", "minItems": 1, "items": resolved_slot_item},
                    "resolution_method": {"type": "string", "minLength": 1},
                    "resolution_evidence": {
                        "type": "array",
                        "minItems": 1,
                        "items": evidence_item,
                    },
                },
                "required": ["resolved_slots", "resolution_method", "resolution_evidence"],
            },
        },
        {
            "if": {
                "properties": {"recommended_strategy": {"const": RouteLabel.CLARIFY.value}},
                "required": ["recommended_strategy"],
            },
            "then": {
                "properties": {
                    "clarification_targets": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                    "clarification_question": {"type": "string", "minLength": 1},
                },
                "required": ["clarification_targets", "clarification_question"],
            },
        },
        {
            "if": {
                "properties": {
                    "recommended_strategy": {
                        "const": RouteLabel.FACE_PRESERVING_REJECTION.value,
                    },
                },
                "required": ["recommended_strategy"],
            },
            "then": {
                "properties": {
                    "rejection_reason": {"type": "string", "minLength": 1},
                },
                "required": ["rejection_reason"],
            },
        },
        {
            "if": {
                "properties": {"recommended_strategy": {"const": RouteLabel.MULTI_STEP.value}},
                "required": ["recommended_strategy"],
            },
            "then": {
                "properties": {
                    "strategy_sequence": {
                        "type": "array",
                        "minItems": 2,
                        "items": build_prediction_json_schema()["definitions"]["route_label"],
                    },
                },
                "required": ["strategy_sequence"],
            },
        },
        {
            "if": {
                "properties": {
                    "recommended_strategy": {"not": {"const": RouteLabel.MULTI_STEP.value}},
                },
                "required": ["recommended_strategy"],
            },
            "then": {
                "properties": {
                    "strategy_sequence": {"type": "array", "maxItems": 0},
                },
            },
        },
        {
            "if": {"properties": {"compound_ambiguity": {"const": True}}},
            "then": {
                "properties": {
                    "ambiguity_types": {"type": "array", "minItems": 2},
                    "compound_ambiguity_count": {"type": "integer", "minimum": 2},
                },
            },
        },
    ]


def build_model_semantic_output_schema() -> dict[str, Any]:
    validate_ownership_contract()
    canonical = build_prediction_json_schema()
    model_fields = model_owned_prediction_fields()
    properties = {
        name: copy.deepcopy(canonical["properties"][name])
        for name in sorted(model_fields)
    }
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://ambiguity-manager.local/schema/v2/t12_model_semantic_output.json",
        "title": "T12ModelSemanticOutput",
        "schema_version": SCHEMA_VERSION,
        "derivation_version": DERIVATION_VERSION,
        "canonical_prediction_schema_hash": canonical_prediction_schema_hash(),
        "description": (
            "Model-facing semantic output derived from canonical schema-v2 prediction "
            "records. Runner-owned and assembled fields are excluded."
        ),
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": sorted(MODEL_OUTPUT_REQUIRED_FIELDS),
        "allOf": _route_conditional_allof(),
        "definitions": copy.deepcopy(canonical.get("definitions", {})),
        "_canonical_prediction_fields": sorted(canonical["properties"]),
        "_post_schema_validation_rules": list(
            __import__(
                "ambiguity_manager.model.semantic_schema_validator",
                fromlist=["POST_SCHEMA_VALIDATION_RULES"],
            ).POST_SCHEMA_VALIDATION_RULES
        ),
    }
    return schema


def model_semantic_output_schema_text() -> str:
    payload = build_model_semantic_output_schema()
    export = {key: value for key, value in payload.items() if not key.startswith("_")}
    return json.dumps(export, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def model_semantic_output_schema_bytes() -> bytes:
    return model_semantic_output_schema_text().encode("utf-8")


def model_semantic_output_schema_for_prompt() -> str:
    schema = build_model_semantic_output_schema()
    export = {key: value for key, value in schema.items() if not key.startswith("_")}
    return json.dumps(export, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_prediction_schema_hash() -> str:
    return sha256_hex(prediction_json_schema_bytes())


def model_semantic_output_schema_hash() -> str:
    export = json.loads(model_semantic_output_schema_text())
    return sha256_hex(canonical_json_bytes(export))


def semantic_schema_path(repo_root: Path | None = None) -> Path:
    from ambiguity_manager.paths import repo_root as default_repo_root

    root = repo_root or default_repo_root()
    return root / "configs" / "model" / "schema" / SEMANTIC_SCHEMA_FILENAME


def write_model_semantic_output_schema(path: Path | None = None) -> Path:
    target = path or semantic_schema_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(model_semantic_output_schema_bytes())
    return target


def extract_model_owned_semantic_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {name: copy.deepcopy(record[name]) for name in sorted(model_owned_prediction_fields())}


# Optional fields that canonical schema-v2 serialisation materialises as JSON null
# when omitted from schema-valid model output. Comparison-only; never mutates inputs.
# Restricted to job-3974-evidenced absent→null classes (plus top-level EvidenceRef.note
# under the same supporting_evidence item schema).
_CANDIDATE_OPTIONAL_NULL_KEYS: frozenset[str] = frozenset({"text", "safety_status"})
_EVIDENCE_OPTIONAL_NULL_KEYS: frozenset[str] = frozenset({"note"})


def _materialize_evidence_item_optional_nulls(item: dict[str, Any]) -> None:
    """Fill missing EvidenceRef optional keys as null for comparison copies only."""
    for key in _EVIDENCE_OPTIONAL_NULL_KEYS:
        if key not in item:
            item[key] = None


def _materialize_optional_canonical_nulls_for_comparison(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Return a deep copy with approved optional absences materialised as null.

    Path-aware and non-mutating. Does not globally equate absent and null.
    """
    normalised = copy.deepcopy(payload)

    candidates = normalised.get("candidate_interpretations")
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            for key in _CANDIDATE_OPTIONAL_NULL_KEYS:
                if key not in candidate:
                    candidate[key] = None

    selected = normalised.get("selected_interpretation")
    if isinstance(selected, dict):
        selected_evidence = selected.get("supporting_evidence")
        if isinstance(selected_evidence, list):
            for item in selected_evidence:
                if isinstance(item, dict):
                    _materialize_evidence_item_optional_nulls(item)

    top_evidence = normalised.get("supporting_evidence")
    if isinstance(top_evidence, list):
        for item in top_evidence:
            if isinstance(item, dict):
                _materialize_evidence_item_optional_nulls(item)

    return normalised


def _assert_semantic_round_trip(
    original_payload: dict[str, Any],
    assembled_record: dict[str, Any],
) -> None:
    extracted = extract_model_owned_semantic_fields(assembled_record)
    left = _materialize_optional_canonical_nulls_for_comparison(original_payload)
    right = _materialize_optional_canonical_nulls_for_comparison(extracted)
    if left != right:
        raise PredictionAssemblyError(
            "semantic round-trip mismatch between validated payload and assembled record"
        )


def validate_semantic_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise SemanticPayloadError("semantic payload must be a JSON object")

    model_fields = model_owned_prediction_fields()
    runner_fields = runner_owned_prediction_fields()

    unknown = sorted(set(payload) - model_fields)
    if unknown:
        raise SemanticPayloadError(f"unknown model fields: {unknown}")

    if "label_eligibility" in payload:
        raise SemanticPayloadError(
            "label_eligibility is runner-owned and must not appear in model output"
        )

    forbidden = sorted(set(payload) & runner_fields)
    if forbidden:
        raise SemanticPayloadError(
            f"runner-owned fields must not appear in semantic payload: {forbidden}"
        )

    missing = sorted(MODEL_OUTPUT_REQUIRED_FIELDS - set(payload))
    if missing:
        raise SemanticPayloadError(f"missing required semantic fields: {missing}")

    from ambiguity_manager.model.semantic_schema_validator import (
        validate_against_model_semantic_schema,
        validate_post_schema_semantic_rules,
    )

    validate_against_model_semantic_schema(payload)
    validate_post_schema_semantic_rules(payload)


def assemble_prediction_record(
    request_context: PredictionRequestContext,
    semantic_payload: dict[str, Any],
    runtime_metadata: PredictionRuntimeMetadata,
    provenance_policy: PredictionProvenancePolicy,
) -> dict[str, Any]:
    if request_context.label_eligibility is None:
        raise PredictionAssemblyError("runner-supplied label_eligibility is required")

    validated_payload = copy.deepcopy(semantic_payload)
    validate_semantic_payload(validated_payload)

    for runner_field in runner_owned_prediction_fields():
        if runner_field in validated_payload:
            raise SemanticPayloadError(
                f"semantic payload must not set runner-owned field {runner_field!r}"
            )

    for field_name, value in validated_payload.items():
        if field_name in request_context.__dataclass_fields__:
            context_value = getattr(request_context, field_name)
            if context_value is not None and value != context_value:
                raise PredictionAssemblyError(
                    f"semantic payload conflicts with request context for {field_name!r}"
                )

    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "id": request_context.request_id,
        "record_class": RecordClass.PREDICTION.value,
        "source_dataset": request_context.source_dataset,
        "source_id": request_context.source_id,
        "original_split": request_context.original_split,
        "group_id": request_context.group_id,
        "split_status": request_context.split_status.value,
        "command": request_context.command,
        "scene_context": request_context.scene_context,
        "dialogue_history": list(request_context.dialogue_history),
        "capability_context": request_context.capability_context,
        "annotation_status": provenance_policy.annotation_status.value,
        "label_confidence": provenance_policy.label_confidence.value,
        "migration_version": None,
        "migrated_from_schema_version": None,
        "v1_legacy": None,
        "mapping_version": request_context.mapping_version,
        "source_license": request_context.source_license,
        "mapping_notes": request_context.mapping_notes,
        "source_metadata": request_context.source_metadata,
        "label_eligibility": request_context.label_eligibility.to_dict(),
        "prediction_metadata": {
            "model_id": runtime_metadata.model_id,
            "prompt_hash": runtime_metadata.prompt_hash,
            "generation_seed": runtime_metadata.generation_seed,
            "raw_model_output": runtime_metadata.raw_model_output,
        },
    }
    record.update(copy.deepcopy(validated_payload))
    try:
        parsed = canonical_record_v2_from_dict(record)
        validated = validate_canonical_record_v2(parsed)
    except SchemaValidationError as exc:
        raise PredictionAssemblyError(str(exc)) from exc

    from ambiguity_manager.schema.v2.records import canonical_record_v2_to_dict

    final_record = canonical_record_v2_to_dict(validated)
    _assert_semantic_round_trip(validated_payload, final_record)
    return final_record
