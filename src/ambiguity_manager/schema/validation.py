"""Canonical schema validation helpers."""

from __future__ import annotations

from typing import Any

from ambiguity_manager.schema.errors import SchemaValidationError
from ambiguity_manager.schema.records import CanonicalRecord, ManagerInput, canonical_record_from_dict
from ambiguity_manager.schema.taxonomies import (
  AnnotationStatus,
  LabelConfidence,
  METRIC_ELIGIBILITY_FIELDS,
  RecordClass,
  RouteLabel,
)
from ambiguity_manager.schema.version import CANONICAL_SCHEMA_VERSION


def _require_non_empty_string(data: dict[str, Any], field_name: str) -> None:
  value = data.get(field_name)
  if not isinstance(value, str) or not value.strip():
    raise SchemaValidationError("required non-empty string", field=field_name)


def validate_manager_input(data: dict[str, Any] | ManagerInput) -> ManagerInput:
  if isinstance(data, ManagerInput):
    record = data
  else:
    if not isinstance(data, dict):
      raise SchemaValidationError("manager input must be an object")
    dialogue_history = data.get("dialogue_history", [])
    if not isinstance(dialogue_history, list) or not all(isinstance(x, str) for x in dialogue_history):
      raise SchemaValidationError("dialogue_history must be a list of strings", field="dialogue_history")
    record = ManagerInput(
      command=str(data.get("command", "")),
      scene_context=data.get("scene_context"),
      dialogue_history=list(dialogue_history),
      capability_context=data.get("capability_context"),
    )

  if not record.command.strip():
    raise SchemaValidationError("required non-empty string", field="command")
  return record


def validate_canonical_record(data: dict[str, Any] | CanonicalRecord) -> CanonicalRecord:
  record = data if isinstance(data, CanonicalRecord) else canonical_record_from_dict(data)

  if record.schema_version != CANONICAL_SCHEMA_VERSION:
    raise SchemaValidationError(
      f"unsupported schema_version {record.schema_version!r}; expected {CANONICAL_SCHEMA_VERSION!r}",
      field="schema_version",
    )

  for field_name in ("id", "command", "source_dataset"):
    value = getattr(record, field_name)
    if not isinstance(value, str) or not value.strip():
      raise SchemaValidationError("required non-empty string", field=field_name)

  if record.record_class not in RecordClass:
    raise SchemaValidationError(
      f"invalid value {record.record_class!r}; expected one of {[m.value for m in RecordClass]}",
      field="record_class",
    )

  if record.record_class == RecordClass.ADJUDICATED_GOLD:
    if record.annotation_status not in (AnnotationStatus.MANUALLY_ANNOTATED, AnnotationStatus.ADJUDICATED):
      raise SchemaValidationError(
        "adjudicated_gold requires annotation_status manually_annotated or adjudicated",
        field="annotation_status",
      )
    if record.label_confidence != LabelConfidence.MANUAL_GOLD:
      raise SchemaValidationError(
        "adjudicated_gold requires label_confidence manual_gold",
        field="record_class",
      )
  elif record.record_class == RecordClass.SOURCE_CONVERTED:
    if record.annotation_status not in (AnnotationStatus.SOURCE_NATIVE, AnnotationStatus.WEAK_MAPPED):
      raise SchemaValidationError(
        "source_converted requires annotation_status source_native or weak_mapped",
        field="annotation_status",
      )

  if record.label_confidence == LabelConfidence.TODO_VERIFY:
    enabled = [name for name in METRIC_ELIGIBILITY_FIELDS if getattr(record.label_eligibility, name)]
    if enabled:
      raise SchemaValidationError(
        f"TODO_VERIFY records cannot enable label_eligibility for {enabled}",
        field="label_eligibility",
      )

  if record.primary_ambiguity_type is not None and record.primary_ambiguity_type not in record.ambiguity_types:
    raise SchemaValidationError(
      "primary_ambiguity_type must appear in ambiguity_types",
      field="primary_ambiguity_type",
    )

  if record.compound_ambiguity:
    if len(record.ambiguity_types) < 2:
      raise SchemaValidationError(
        "compound_ambiguity requires at least two ambiguity_types",
        field="compound_ambiguity",
      )
    if record.compound_ambiguity_count < 2:
      raise SchemaValidationError(
        "compound_ambiguity requires compound_ambiguity_count >= 2",
        field="compound_ambiguity_count",
      )

  if record.ambiguity_present is True and record.compound_ambiguity_count > 0:
    if record.compound_ambiguity_count != len(record.ambiguity_types):
      raise SchemaValidationError(
        "compound_ambiguity_count must equal len(ambiguity_types) when ambiguity_present is true",
        field="compound_ambiguity_count",
      )

  if record.recommended_strategy == RouteLabel.MULTI_STEP:
    if len(record.strategy_sequence) < 2:
      raise SchemaValidationError(
        "multi_step requires strategy_sequence with at least two steps",
        field="strategy_sequence",
      )
  elif record.strategy_sequence:
    raise SchemaValidationError(
      "strategy_sequence must be empty unless recommended_strategy is multi_step",
      field="strategy_sequence",
    )

  return record


def validate_canonical_record_dict(data: dict[str, Any]) -> CanonicalRecord:
  _require_non_empty_string(data, "id")
  _require_non_empty_string(data, "command")
  _require_non_empty_string(data, "source_dataset")
  _require_non_empty_string(data, "schema_version")
  return validate_canonical_record(data)
