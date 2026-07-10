"""Canonical schema v2 validation helpers."""

from __future__ import annotations

from typing import Any

from ambiguity_manager.schema.v2.errors import SchemaValidationError
from ambiguity_manager.schema.v2.records import CanonicalRecordV2, canonical_record_v2_from_dict
from ambiguity_manager.schema.v2.taxonomies import (
  AnnotationStatus,
  LabelConfidence,
  METRIC_ELIGIBILITY_FIELDS,
  RecordClass,
  RouteLabel,
)
from ambiguity_manager.schema.v2.version import SCHEMA_VERSION


def _require_non_empty_string(data: dict[str, Any], field_name: str) -> None:
  value = data.get(field_name)
  if not isinstance(value, str) or not value.strip():
    raise SchemaValidationError("required non-empty string", field=field_name)


def _is_gold_or_source(record: CanonicalRecordV2) -> bool:
  return record.record_class in (RecordClass.SOURCE_CONVERTED, RecordClass.ADJUDICATED_GOLD)


def _is_prediction(record: CanonicalRecordV2) -> bool:
  return record.record_class == RecordClass.PREDICTION


def validate_canonical_record_v2(data: dict[str, Any] | CanonicalRecordV2) -> CanonicalRecordV2:
  record = data if isinstance(data, CanonicalRecordV2) else canonical_record_v2_from_dict(data)

  if record.schema_version != SCHEMA_VERSION:
    raise SchemaValidationError(
      f"unsupported schema_version {record.schema_version!r}; expected {SCHEMA_VERSION!r}",
      field="schema_version",
    )

  for field_name in ("id", "command", "source_dataset"):
    value = getattr(record, field_name)
    if not isinstance(value, str) or not value.strip():
      raise SchemaValidationError("required non-empty string", field=field_name)

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
  elif record.record_class == RecordClass.PREDICTION:
    if record.prediction_metadata is None:
      raise SchemaValidationError(
        "prediction records require prediction_metadata",
        field="prediction_metadata",
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

  if record.selected_interpretation is not None:
    if not record.selected_interpretation.supporting_evidence:
      raise SchemaValidationError(
        "selected_interpretation requires non-empty supporting_evidence",
        field="selected_interpretation",
      )
    candidate_ids = {item.frame_id for item in record.candidate_interpretations}
    if record.selected_interpretation.frame_id not in candidate_ids:
      raise SchemaValidationError(
        "selected_interpretation.frame_id must reference a candidate frame",
        field="selected_interpretation",
      )

  if _is_prediction(record):
    if record.label_eligibility.risk and record.risk_level is None:
      raise SchemaValidationError(
        "prediction records with risk eligibility require risk_level",
        field="risk_level",
      )
    if record.label_eligibility.capability and record.capability_status is None:
      raise SchemaValidationError(
        "prediction records with capability eligibility require capability_status",
        field="capability_status",
      )
    if record.recommended_strategy == RouteLabel.SILENTLY_RESOLVE:
      if not record.resolved_slots:
        raise SchemaValidationError(
          "silently_resolve predictions require resolved_slots",
          field="resolved_slots",
        )
      if not record.resolution_method:
        raise SchemaValidationError(
          "silently_resolve predictions require resolution_method",
          field="resolution_method",
        )
      if not record.resolution_evidence:
        raise SchemaValidationError(
          "silently_resolve predictions require resolution_evidence",
          field="resolution_evidence",
        )
    if record.recommended_strategy == RouteLabel.CLARIFY:
      if not record.clarification_targets:
        raise SchemaValidationError(
          "clarify predictions require clarification_targets",
          field="clarification_targets",
        )
      if not record.clarification_question:
        raise SchemaValidationError(
          "clarify predictions require clarification_question",
          field="clarification_question",
        )
    if record.recommended_strategy == RouteLabel.FACE_PRESERVING_REJECTION:
      if not record.rejection_reason:
        raise SchemaValidationError(
          "face_preserving_rejection predictions require rejection_reason",
          field="rejection_reason",
        )

  return record


def validate_canonical_record_v2_dict(data: dict[str, Any]) -> CanonicalRecordV2:
  _require_non_empty_string(data, "id")
  _require_non_empty_string(data, "command")
  _require_non_empty_string(data, "source_dataset")
  _require_non_empty_string(data, "schema_version")
  return validate_canonical_record_v2(data)
