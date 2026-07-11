"""Deterministic JSON Schema export derived from schema v2 Python definitions.

The Python dataclasses and StrEnum taxonomies in ``taxonomies.py`` and
``records.py`` are authoritative. This module constructs a JSON Schema document
from those definitions for interchange documentation only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ambiguity_manager.schema.v2.taxonomies import (
  AmbiguityType,
  AnnotationStatus,
  CapabilityStatus,
  CPC_SLOT_NAMES,
  CPCSlotStatus,
  LabelConfidence,
  METRIC_ELIGIBILITY_FIELDS,
  RecordClass,
  RiskLevel,
  RouteLabel,
  SafetyStatus,
  SplitStatus,
)
from ambiguity_manager.schema.v2.version import SCHEMA_VERSION

SCHEMA_JSON_FILENAME = "schema.json"


def _enum_values(enum_cls: type) -> list[str]:
  return sorted(member.value for member in enum_cls)


def _string_enum(enum_cls: type) -> dict[str, Any]:
  return {"type": "string", "enum": _enum_values(enum_cls)}


def _nullable_string_enum(enum_cls: type) -> dict[str, Any]:
  return {"oneOf": [{"type": "null"}, _string_enum(enum_cls)]}


def _cpc_slot_schema() -> dict[str, Any]:
  return {
    "type": "object",
    "additionalProperties": False,
    "properties": {
      "value": {"type": ["string", "null"]},
      "status": _string_enum(CPCSlotStatus),
    },
    "required": ["value", "status"],
  }


def _cpc_schema() -> dict[str, Any]:
  return {
    "type": "object",
    "additionalProperties": False,
    "properties": {name: _cpc_slot_schema() for name in CPC_SLOT_NAMES},
    "required": list(CPC_SLOT_NAMES),
  }


def _evidence_ref_schema() -> dict[str, Any]:
  return {
    "type": "object",
    "additionalProperties": False,
    "properties": {
      "source": {"type": "string", "minLength": 1},
      "span": {"type": ["string", "null"]},
      "note": {"type": ["string", "null"]},
    },
    "required": ["source"],
  }


def _label_eligibility_schema() -> dict[str, Any]:
  return {
    "type": "object",
    "additionalProperties": False,
    "properties": {name: {"type": "boolean"} for name in METRIC_ELIGIBILITY_FIELDS},
    "required": list(METRIC_ELIGIBILITY_FIELDS),
  }


def _shared_record_properties() -> dict[str, Any]:
  return {
    "schema_version": {"type": "string", "const": SCHEMA_VERSION},
    "id": {"type": "string", "minLength": 1},
    "record_class": _string_enum(RecordClass),
    "source_dataset": {"type": "string", "minLength": 1},
    "source_id": {"type": ["string", "null"]},
    "original_split": {"type": ["string", "null"]},
    "group_id": {"type": ["string", "null"]},
    "split_status": _string_enum(SplitStatus),
    "command": {"type": "string", "minLength": 1},
    "scene_context": {"type": ["string", "null"]},
    "dialogue_history": {"type": "array", "items": {"type": "string"}},
    "capability_context": {"type": ["string", "null"]},
    "speech_act": {"type": ["string", "null"]},
    "intent_summary": {"type": ["string", "null"]},
    "cpc": _cpc_schema(),
    "candidate_interpretations": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
          "frame_id": {"type": "string", "minLength": 1},
          "text": {"type": ["string", "null"]},
          "cpc": _cpc_schema(),
          "confidence": {"type": ["number", "null"]},
          "safety_status": _nullable_string_enum(SafetyStatus),
        },
        "required": ["frame_id", "cpc"],
      },
    },
    "selected_interpretation": {
      "oneOf": [
        {"type": "null"},
        {
          "type": "object",
          "additionalProperties": False,
          "properties": {
            "frame_id": {"type": "string", "minLength": 1},
            "supporting_evidence": {
              "type": "array",
              "items": _evidence_ref_schema(),
              "minItems": 1,
            },
          },
          "required": ["frame_id", "supporting_evidence"],
        },
      ],
    },
    "unresolved_slots": {
      "type": "array",
      "items": {
        "oneOf": [
          {"type": "string", "minLength": 1},
          {
            "type": "object",
            "additionalProperties": False,
            "properties": {
              "slot_name": {"type": "string", "minLength": 1},
              "reason": {"type": ["string", "null"]},
            },
            "required": ["slot_name"],
          },
        ],
      },
    },
    "supporting_evidence": {"type": "array", "items": _evidence_ref_schema()},
    "ambiguity_present": {"type": ["boolean", "null"]},
    "ambiguity_types": {"type": "array", "items": _string_enum(AmbiguityType)},
    "primary_ambiguity_type": _nullable_string_enum(AmbiguityType),
    "compound_ambiguity": {"type": "boolean"},
    "compound_ambiguity_count": {"type": "integer"},
    "risk_relevant": {"type": "boolean"},
    "risk_level": _nullable_string_enum(RiskLevel),
    "capability_status": _nullable_string_enum(CapabilityStatus),
    "recommended_strategy": _nullable_string_enum(RouteLabel),
    "strategy_sequence": {"type": "array", "items": _string_enum(RouteLabel)},
    "clarification_question": {"type": ["string", "null"]},
    "clarification_subtype": {"type": ["string", "null"]},
    "clarification_targets": {"type": "array", "items": {"type": "string"}},
    "rejection_reason": {"type": ["string", "null"]},
    "resolved_slots": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
          "slot_name": {"type": "string", "minLength": 1},
          "value": {"type": "string", "minLength": 1},
        },
        "required": ["slot_name", "value"],
      },
    },
    "resolution_method": {"type": ["string", "null"]},
    "resolution_evidence": {"type": "array", "items": _evidence_ref_schema()},
    "context_sampling_uncertainty": {
      "oneOf": [
        {"type": "null"},
        {
          "type": "object",
          "additionalProperties": False,
          "properties": {
            "score": {"type": ["number", "null"]},
            "variant_count": {"type": ["integer", "null"]},
            "agreement": {"type": ["number", "null"]},
          },
        },
      ],
    },
    "migration_version": {"type": ["string", "null"]},
    "migrated_from_schema_version": {"type": ["string", "null"]},
    "v1_legacy": {
      "oneOf": [
        {"type": "null"},
        {
          "type": "object",
          "additionalProperties": False,
          "properties": {
            "missing_slots": {"type": "array", "items": {"type": "string"}},
            "gold_clarification_question": {"type": ["string", "null"]},
            "resolved_interpretation": {"type": ["string", "null"]},
            "intent": {"type": ["string", "null"]},
            "slots": {"type": "object"},
          },
        },
      ],
    },
    "prediction_metadata": {
      "oneOf": [
        {"type": "null"},
        {
          "type": "object",
          "additionalProperties": False,
          "properties": {
            "model_id": {"type": ["string", "null"]},
            "prompt_hash": {"type": ["string", "null"]},
            "generation_seed": {"type": ["integer", "null"]},
            "raw_model_output": {"type": ["string", "null"]},
          },
        },
      ],
    },
    "annotation_status": _string_enum(AnnotationStatus),
    "label_confidence": _string_enum(LabelConfidence),
    "label_eligibility": _label_eligibility_schema(),
    "mapping_version": {"type": ["string", "null"]},
    "source_license": {"type": ["string", "null"]},
    "mapping_notes": {"type": ["string", "null"]},
    "source_metadata": {"oneOf": [{"type": "null"}, {"type": "object"}]},
  }


def _gold_source_record_schema() -> dict[str, Any]:
  properties = _shared_record_properties()
  properties["record_class"] = {
    "type": "string",
    "enum": [RecordClass.SOURCE_CONVERTED.value, RecordClass.ADJUDICATED_GOLD.value],
  }
  properties["prediction_metadata"] = {"type": "null"}
  return {
    "type": "object",
    "additionalProperties": False,
    "properties": properties,
    "required": [
      "schema_version",
      "id",
      "record_class",
      "source_dataset",
      "command",
      "annotation_status",
      "label_confidence",
      "label_eligibility",
      "cpc",
    ],
    "description": (
      "Gold or source-converted record. risk_level, capability_status, and other "
      "labels may be null when genuinely unavailable and metric-ineligible."
    ),
  }


def _prediction_record_schema() -> dict[str, Any]:
  properties = _shared_record_properties()
  properties["record_class"] = {"type": "string", "const": RecordClass.PREDICTION.value}
  properties["prediction_metadata"] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
      "model_id": {"type": ["string", "null"]},
      "prompt_hash": {"type": ["string", "null"]},
      "generation_seed": {"type": ["integer", "null"]},
      "raw_model_output": {"type": ["string", "null"]},
    },
  }
  return {
    "type": "object",
    "additionalProperties": False,
    "properties": properties,
    "required": [
      "schema_version",
      "id",
      "record_class",
      "source_dataset",
      "command",
      "annotation_status",
      "label_confidence",
      "label_eligibility",
      "cpc",
      "prediction_metadata",
    ],
    "description": (
      "Model prediction record. When label_eligibility enables a metric, the "
      "corresponding field must be non-null (enforced by Python validators). "
      "silently_resolve requires resolved_slots, resolution_method, and "
      "resolution_evidence; clarify requires clarification_targets and "
      "clarification_question; face_preserving_rejection requires rejection_reason."
    ),
  }


def build_prediction_json_schema() -> dict[str, Any]:
  """Export only the schema-v2 prediction record branch."""
  prediction = _prediction_record_schema()
  return {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://ambiguity-manager.local/schema/v2/prediction_record.json",
    "title": "CanonicalRecordV2Prediction",
    "schema_version": SCHEMA_VERSION,
    "description": (
      "Prediction-only export derived from ambiguity_manager.schema.v2 Python "
      "definitions. Gold/source branches are excluded."
    ),
    **prediction,
    "definitions": {
      "risk_level": _string_enum(RiskLevel),
      "capability_status": _string_enum(CapabilityStatus),
      "route_label": _string_enum(RouteLabel),
      "ambiguity_type": _string_enum(AmbiguityType),
      "cpc_slot_status": _string_enum(CPCSlotStatus),
      "record_class": {"type": "string", "const": RecordClass.PREDICTION.value},
    },
  }


def prediction_json_schema_text() -> str:
  """Return deterministic prediction-only JSON Schema text."""
  return json.dumps(build_prediction_json_schema(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def prediction_json_schema_bytes() -> bytes:
  """Return deterministic prediction-only JSON Schema bytes."""
  return prediction_json_schema_text().encode("utf-8")


def build_canonical_record_v2_json_schema() -> dict[str, Any]:
  """Build the JSON Schema document from authoritative Python definitions."""
  return {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://ambiguity-manager.local/schema/v2/canonical_record.json",
    "title": "CanonicalRecordV2",
    "schema_version": SCHEMA_VERSION,
    "description": (
      "Export derived from ambiguity_manager.schema.v2 Python definitions. "
      "Not an independent source of truth; regenerate via json_schema.py."
    ),
    "oneOf": [
      _gold_source_record_schema(),
      _prediction_record_schema(),
    ],
    "definitions": {
      "risk_level": _string_enum(RiskLevel),
      "capability_status": _string_enum(CapabilityStatus),
      "route_label": _string_enum(RouteLabel),
      "ambiguity_type": _string_enum(AmbiguityType),
      "cpc_slot_status": _string_enum(CPCSlotStatus),
      "record_class": _string_enum(RecordClass),
    },
  }


def canonical_record_v2_json_schema_text() -> str:
  """Return deterministic JSON Schema text with canonical LF newlines."""
  return json.dumps(build_canonical_record_v2_json_schema(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def canonical_record_v2_json_schema_bytes() -> bytes:
  """Return deterministic JSON Schema bytes (UTF-8, LF newlines)."""
  return canonical_record_v2_json_schema_text().encode("utf-8")


def schema_json_path() -> Path:
  return Path(__file__).resolve().parent / SCHEMA_JSON_FILENAME


def write_schema_json(path: Path | None = None) -> Path:
  target = path or schema_json_path()
  target.write_bytes(canonical_record_v2_json_schema_bytes())
  return target
