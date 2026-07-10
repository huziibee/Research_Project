"""Deterministic v1-to-v2 canonical record migration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ambiguity_manager.schema.records import canonical_record_to_dict
from ambiguity_manager.schema.validation import validate_canonical_record
from ambiguity_manager.schema.v2.records import (
  CandidateInterpretationFrame,
  CanonicalRecordV2,
  ContextSamplingUncertainty,
  LabelEligibility,
  UnresolvedSlot,
  V1LegacyProvenance,
  canonical_record_v2_to_dict,
)
from ambiguity_manager.schema.v2.taxonomies import (
  AmbiguityType,
  AnnotationStatus,
  CapabilityStatus,
  LabelConfidence,
  REJECTED_LEGACY_VALUES,
  RecordClass,
  RiskLevel,
  RouteLabel,
  SplitStatus,
  V1_LEGACY_CAPABILITY_VALUES,
  V1_LEGACY_RISK_VALUES,
)
from ambiguity_manager.schema.v2.validation import validate_canonical_record_v2
from ambiguity_manager.schema.v2.version import SCHEMA_VERSION
from ambiguity_manager.migration.slot_mapping import map_legacy_slots_to_cpc

MIGRATION_VERSION = "v1_to_v2-1.0.0"
MIGRATED_FROM_SCHEMA_VERSION = "1.0.0"

UNMAPPABLE_FIELD_REASONS: tuple[str, ...] = (
  "not_present_in_v1:selected_interpretation",
  "not_present_in_v1:supporting_evidence",
  "not_present_in_v1:context_sampling_uncertainty",
  "not_present_in_v1:resolved_slots",
  "not_present_in_v1:resolution_method",
  "not_present_in_v1:resolution_evidence",
  "not_present_in_v1:rejection_reason",
  "not_present_in_v1:speech_act",
)


class MigrationError(ValueError):
  """Raised when a v1 record cannot be migrated."""


@dataclass
class MigrationAccounting:
  records_migrated: int = 0
  legacy_risk_mappings: dict[str, int] = field(default_factory=dict)
  legacy_capability_mappings: dict[str, int] = field(default_factory=dict)
  rejected_legacy_values: dict[str, int] = field(default_factory=dict)
  unmapped_slot_keys_by_dataset: dict[str, dict[str, int]] = field(default_factory=dict)
  unmappable_fields: dict[str, int] = field(default_factory=dict)

  def record_legacy_risk(self, old: str, new: str) -> None:
    key = f"{old}->{new}"
    self.legacy_risk_mappings[key] = self.legacy_risk_mappings.get(key, 0) + 1

  def record_legacy_capability(self, old: str, new: str) -> None:
    key = f"{old}->{new}"
    self.legacy_capability_mappings[key] = self.legacy_capability_mappings.get(key, 0) + 1

  def record_rejected(self, value: str) -> None:
    self.rejected_legacy_values[value] = self.rejected_legacy_values.get(value, 0) + 1

  def record_unmapped_slot_key(self, dataset: str, key: str) -> None:
    bucket = self.unmapped_slot_keys_by_dataset.setdefault(dataset, {})
    bucket[key] = bucket.get(key, 0) + 1

  def record_unmappable(self, reason: str) -> None:
    self.unmappable_fields[reason] = self.unmappable_fields.get(reason, 0) + 1

  def merge(self, other: "MigrationAccounting") -> None:
    self.records_migrated += other.records_migrated
    for mapping, count in other.legacy_risk_mappings.items():
      self.legacy_risk_mappings[mapping] = self.legacy_risk_mappings.get(mapping, 0) + count
    for mapping, count in other.legacy_capability_mappings.items():
      self.legacy_capability_mappings[mapping] = (
        self.legacy_capability_mappings.get(mapping, 0) + count
      )
    for value, count in other.rejected_legacy_values.items():
      self.rejected_legacy_values[value] = self.rejected_legacy_values.get(value, 0) + count
    for dataset, keys in other.unmapped_slot_keys_by_dataset.items():
      bucket = self.unmapped_slot_keys_by_dataset.setdefault(dataset, {})
      for key, count in keys.items():
        bucket[key] = bucket.get(key, 0) + count
    for reason, count in other.unmappable_fields.items():
      self.unmappable_fields[reason] = self.unmappable_fields.get(reason, 0) + count

  def to_dict(self) -> dict[str, Any]:
    return {
      "records_migrated": self.records_migrated,
      "legacy_risk_mappings": dict(sorted(self.legacy_risk_mappings.items())),
      "legacy_capability_mappings": dict(sorted(self.legacy_capability_mappings.items())),
      "rejected_legacy_values": dict(sorted(self.rejected_legacy_values.items())),
      "unmapped_slot_keys_by_dataset": {
        dataset: dict(sorted(keys.items()))
        for dataset, keys in sorted(self.unmapped_slot_keys_by_dataset.items())
      },
      "unmappable_fields": dict(sorted(self.unmappable_fields.items())),
    }


def _map_risk_level(raw: Any, accounting: MigrationAccounting) -> RiskLevel | None:
  if raw is None:
    return None
  if not isinstance(raw, str):
    raise MigrationError(f"invalid risk_level type: {type(raw)!r}")
  if raw in REJECTED_LEGACY_VALUES:
    accounting.record_rejected(raw)
    raise MigrationError(f"unsupported legacy risk_level value: {raw!r}")
  if raw in V1_LEGACY_RISK_VALUES:
    accounting.record_legacy_risk(raw, RiskLevel.UNKNOWN.value)
    return RiskLevel.UNKNOWN
  try:
    return RiskLevel(raw)
  except ValueError as exc:
    raise MigrationError(f"unsupported risk_level value: {raw!r}") from exc


def _map_capability_status(raw: Any, accounting: MigrationAccounting) -> CapabilityStatus | None:
  if raw is None:
    return None
  if not isinstance(raw, str):
    raise MigrationError(f"invalid capability_status type: {type(raw)!r}")
  if raw in REJECTED_LEGACY_VALUES:
    accounting.record_rejected(raw)
    raise MigrationError(f"unsupported legacy capability_status value: {raw!r}")
  if raw in V1_LEGACY_CAPABILITY_VALUES:
    accounting.record_legacy_capability(raw, CapabilityStatus.CONDITIONAL.value)
    return CapabilityStatus.CONDITIONAL
  try:
    return CapabilityStatus(raw)
  except ValueError as exc:
    raise MigrationError(f"unsupported capability_status value: {raw!r}") from exc


def _candidate_frame_id(record_id: str, index: int) -> str:
  return f"{record_id}:candidate:{index}"


def migrate_v1_dict_to_v2(
  v1_data: dict[str, Any],
  accounting: MigrationAccounting | None = None,
) -> CanonicalRecordV2:
  acc = accounting or MigrationAccounting()
  v1_record = validate_canonical_record(v1_data)
  v1 = canonical_record_to_dict(v1_record)

  cpc, _unmapped_slots, unmapped_keys = map_legacy_slots_to_cpc(
    v1_record.source_dataset,
    dict(v1.get("slots") or {}),
  )
  for key in unmapped_keys:
    acc.record_unmapped_slot_key(v1_record.source_dataset, key)

  candidate_frames: list[CandidateInterpretationFrame] = []
  for index, candidate in enumerate(v1_record.candidate_interpretations):
    safety = candidate.safety_status.value if candidate.safety_status is not None else None
    from ambiguity_manager.schema.v2.taxonomies import SafetyStatus

    safety_status = SafetyStatus(safety) if safety is not None else None
    candidate_frames.append(
      CandidateInterpretationFrame(
        frame_id=_candidate_frame_id(v1_record.id, index),
        text=candidate.text,
        confidence=candidate.confidence,
        safety_status=safety_status,
      )
    )

  unresolved = [UnresolvedSlot(slot_name=name) for name in v1_record.missing_slots]

  v1_legacy = V1LegacyProvenance(
    missing_slots=list(v1_record.missing_slots),
    gold_clarification_question=v1_record.gold_clarification_question,
    resolved_interpretation=v1_record.resolved_interpretation,
    intent=v1_record.intent,
    slots=dict(v1.get("slots") or {}),
  )

  for reason in UNMAPPABLE_FIELD_REASONS:
    acc.record_unmappable(reason)

  record = CanonicalRecordV2(
    schema_version=SCHEMA_VERSION,
    id=v1_record.id,
    record_class=RecordClass(v1_record.record_class.value),
    source_dataset=v1_record.source_dataset,
    source_id=v1_record.source_id,
    original_split=v1_record.original_split,
    group_id=v1_record.group_id,
    split_status=SplitStatus(v1_record.split_status.value),
    command=v1_record.command,
    scene_context=v1_record.scene_context,
    dialogue_history=list(v1_record.dialogue_history),
    capability_context=v1_record.capability_context,
    speech_act=None,
    intent_summary=v1_record.intent,
    cpc=cpc,
    candidate_interpretations=candidate_frames,
    selected_interpretation=None,
    unresolved_slots=unresolved,
    supporting_evidence=[],
    ambiguity_present=v1_record.ambiguity_present,
    ambiguity_types=[AmbiguityType(v.value) for v in v1_record.ambiguity_types],
    primary_ambiguity_type=(
      AmbiguityType(v1_record.primary_ambiguity_type.value)
      if v1_record.primary_ambiguity_type is not None
      else None
    ),
    compound_ambiguity=v1_record.compound_ambiguity,
    compound_ambiguity_count=v1_record.compound_ambiguity_count,
    risk_relevant=v1_record.risk_relevant,
    risk_level=_map_risk_level(v1.get("risk_level"), acc),
    capability_status=_map_capability_status(v1.get("capability_status"), acc),
    recommended_strategy=(
      RouteLabel(v1_record.recommended_strategy.value)
      if v1_record.recommended_strategy is not None
      else None
    ),
    strategy_sequence=[RouteLabel(v.value) for v in v1_record.strategy_sequence],
    clarification_question=v1_record.gold_clarification_question,
    clarification_subtype=v1_record.clarification_subtype,
    clarification_targets=[],
    rejection_reason=None,
    resolved_slots=[],
    resolution_method=None,
    resolution_evidence=[],
    context_sampling_uncertainty=ContextSamplingUncertainty(),
    migration_version=MIGRATION_VERSION,
    migrated_from_schema_version=MIGRATED_FROM_SCHEMA_VERSION,
    v1_legacy=v1_legacy,
    prediction_metadata=None,
    annotation_status=AnnotationStatus(v1_record.annotation_status.value),
    label_confidence=LabelConfidence(v1_record.label_confidence.value),
    label_eligibility=LabelEligibility.from_dict(v1_record.label_eligibility.to_dict()),
    mapping_version=v1_record.mapping_version,
    source_license=v1_record.source_license,
    mapping_notes=v1_record.mapping_notes,
    source_metadata=v1_record.source_metadata,
  )

  validate_canonical_record_v2(record)
  acc.records_migrated += 1
  return record


def migrate_v1_dict_to_v2_dict(
  v1_data: dict[str, Any],
  accounting: MigrationAccounting | None = None,
) -> dict[str, Any]:
  record = migrate_v1_dict_to_v2(v1_data, accounting)
  return canonical_record_v2_to_dict(record)
