"""Standards-compliant JSON Schema validation for T12 model semantic output."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from ambiguity_manager.model.prediction_contract import (
    SemanticPayloadError,
    build_model_semantic_output_schema,
)


def model_semantic_schema_validator() -> Draft202012Validator:
    schema = build_model_semantic_output_schema()
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise SemanticPayloadError(f"invalid model semantic schema: {exc}") from exc
    return Draft202012Validator(schema)


def validate_against_model_semantic_schema(payload: dict[str, Any]) -> None:
    validator = model_semantic_schema_validator()
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if not errors:
        return
    first = errors[0]
    path = ".".join(str(part) for part in first.path) or "<root>"
    raise SemanticPayloadError(f"schema validation failed at {path}: {first.message}")


POST_SCHEMA_VALIDATION_RULES: tuple[str, ...] = (
    "selected_interpretation.frame_id must reference candidate_interpretations",
    "primary_ambiguity_type must appear in ambiguity_types when set",
    "compound_ambiguity requires at least two ambiguity_types",
    "compound_ambiguity requires compound_ambiguity_count >= 2",
    "compound_ambiguity_count must equal len(ambiguity_types) when ambiguity_present is true",
)


def validate_post_schema_semantic_rules(payload: dict[str, Any]) -> None:
    """Enforce semantic rules not fully captured by JSON Schema conditionals."""
    selected = payload.get("selected_interpretation")
    candidates = payload.get("candidate_interpretations", [])
    if selected is not None:
        if not isinstance(selected, dict):
            raise SemanticPayloadError("selected_interpretation must be an object or null")
        candidate_ids = {
            item.get("frame_id")
            for item in candidates
            if isinstance(item, dict) and isinstance(item.get("frame_id"), str)
        }
        frame_id = selected.get("frame_id")
        if frame_id not in candidate_ids:
            raise SemanticPayloadError(
                "selected_interpretation.frame_id must reference a candidate frame"
            )

    ambiguity_types = payload.get("ambiguity_types", [])
    primary = payload.get("primary_ambiguity_type")
    if primary is not None and primary not in ambiguity_types:
        raise SemanticPayloadError("primary_ambiguity_type must appear in ambiguity_types")

    compound = bool(payload.get("compound_ambiguity", False))
    compound_count = int(payload.get("compound_ambiguity_count", 0))
    if compound:
        if len(ambiguity_types) < 2:
            raise SemanticPayloadError("compound_ambiguity requires at least two ambiguity_types")
        if compound_count < 2:
            raise SemanticPayloadError("compound_ambiguity requires compound_ambiguity_count >= 2")

    if payload.get("ambiguity_present") is True and compound_count > 0:
        if compound_count != len(ambiguity_types):
            raise SemanticPayloadError(
                "compound_ambiguity_count must equal len(ambiguity_types) when ambiguity_present is true"
            )
