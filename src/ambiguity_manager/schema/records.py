"""Canonical dataset record dataclasses."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ambiguity_manager.schema.taxonomies import (
  AmbiguityType,
  AnnotationStatus,
  CapabilityStatus,
  LabelConfidence,
  METRIC_ELIGIBILITY_FIELDS,
  RecordClass,
  RiskLevel,
  RouteLabel,
  SafetyStatus,
  SplitStatus,
)
from ambiguity_manager.schema.version import CANONICAL_SCHEMA_VERSION


def _enum_value(value: Any) -> Any:
  return value.value if hasattr(value, "value") else value


@dataclass
class ManagerInput:
  command: str
  scene_context: str | None = None
  dialogue_history: list[str] = field(default_factory=list)
  capability_context: str | None = None


@dataclass
class CandidateInterpretation:
  text: str
  confidence: float | None = None
  safety_status: SafetyStatus | None = None


@dataclass
class LabelEligibility:
  routing: bool = False
  ambiguity: bool = False
  risk: bool = False
  capability: bool = False
  clarification_decision: bool = False
  clarification_target: bool = False
  intent_slots: bool = False
  rejection: bool = False
  compound_sequence: bool = False
  context_benefit: bool = False

  def to_dict(self) -> dict[str, bool]:
    return {name: getattr(self, name) for name in METRIC_ELIGIBILITY_FIELDS}

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "LabelEligibility":
    return cls(**{name: bool(data.get(name, False)) for name in METRIC_ELIGIBILITY_FIELDS})


@dataclass
class CanonicalRecord:
  """Source-converted or adjudicated-gold dataset record (not model predictions)."""

  id: str
  record_class: RecordClass
  source_dataset: str
  command: str
  annotation_status: AnnotationStatus
  label_confidence: LabelConfidence
  label_eligibility: LabelEligibility
  schema_version: str = CANONICAL_SCHEMA_VERSION
  source_id: str | None = None
  original_split: str | None = None
  group_id: str | None = None
  split_status: SplitStatus = SplitStatus.UNSPLIT
  scene_context: str | None = None
  dialogue_history: list[str] = field(default_factory=list)
  capability_context: str | None = None
  candidate_interpretations: list[CandidateInterpretation] = field(default_factory=list)
  ambiguity_present: bool | None = None
  ambiguity_types: list[AmbiguityType] = field(default_factory=list)
  primary_ambiguity_type: AmbiguityType | None = None
  compound_ambiguity: bool = False
  compound_ambiguity_count: int = 0
  missing_slots: list[str] = field(default_factory=list)
  risk_relevant: bool = False
  risk_level: RiskLevel | None = None
  capability_status: CapabilityStatus | None = None
  recommended_strategy: RouteLabel | None = None
  strategy_sequence: list[RouteLabel] = field(default_factory=list)
  gold_clarification_question: str | None = None
  clarification_subtype: str | None = None
  resolved_interpretation: str | None = None
  intent: str | None = None
  slots: dict[str, Any] = field(default_factory=dict)
  mapping_version: str | None = None
  source_license: str | None = None
  mapping_notes: str | None = None
  source_metadata: dict[str, Any] | None = None


def _parse_enum(enum_cls: type, value: Any, field_name: str) -> Any:
  if value is None:
    return None
  try:
    return enum_cls(value)
  except ValueError as exc:
    from ambiguity_manager.schema.errors import SchemaValidationError

    raise SchemaValidationError(
      f"invalid value {value!r}; expected one of {[m.value for m in enum_cls]}",
      field=field_name,
    ) from exc


def _parse_candidate(data: dict[str, Any]) -> CandidateInterpretation:
  if not isinstance(data, dict):
    from ambiguity_manager.schema.errors import SchemaValidationError

    raise SchemaValidationError("candidate_interpretations entries must be objects")
  text = data.get("text")
  if not isinstance(text, str) or not text.strip():
    from ambiguity_manager.schema.errors import SchemaValidationError

    raise SchemaValidationError("text is required and must be a non-empty string", field="text")
  confidence = data.get("confidence")
  if confidence is not None and not isinstance(confidence, (int, float)):
    from ambiguity_manager.schema.errors import SchemaValidationError

    raise SchemaValidationError("confidence must be a number or null", field="confidence")
  safety = data.get("safety_status")
  safety_status = _parse_enum(SafetyStatus, safety, "safety_status") if safety is not None else None
  return CandidateInterpretation(
    text=text,
    confidence=float(confidence) if confidence is not None else None,
    safety_status=safety_status,
  )


def canonical_record_from_dict(data: dict[str, Any]) -> CanonicalRecord:
  from ambiguity_manager.schema.errors import SchemaValidationError

  if not isinstance(data, dict):
    raise SchemaValidationError("record must be a JSON object")

  label_eligibility_raw = data.get("label_eligibility")
  if not isinstance(label_eligibility_raw, dict):
    raise SchemaValidationError("label_eligibility is required and must be an object", field="label_eligibility")

  ambiguity_types_raw = data.get("ambiguity_types", [])
  if not isinstance(ambiguity_types_raw, list):
    raise SchemaValidationError("ambiguity_types must be a list", field="ambiguity_types")

  strategy_sequence_raw = data.get("strategy_sequence", [])
  if not isinstance(strategy_sequence_raw, list):
    raise SchemaValidationError("strategy_sequence must be a list", field="strategy_sequence")

  dialogue_history = data.get("dialogue_history", [])
  if not isinstance(dialogue_history, list) or not all(isinstance(x, str) for x in dialogue_history):
    raise SchemaValidationError("dialogue_history must be a list of strings", field="dialogue_history")

  missing_slots = data.get("missing_slots", [])
  if not isinstance(missing_slots, list) or not all(isinstance(x, str) for x in missing_slots):
    raise SchemaValidationError("missing_slots must be a list of strings", field="missing_slots")

  candidates_raw = data.get("candidate_interpretations", [])
  if not isinstance(candidates_raw, list):
    raise SchemaValidationError(
      "candidate_interpretations must be a list",
      field="candidate_interpretations",
    )

  slots = data.get("slots", {})
  if not isinstance(slots, dict):
    raise SchemaValidationError("slots must be an object", field="slots")

  source_metadata = data.get("source_metadata")
  if source_metadata is not None and not isinstance(source_metadata, dict):
    raise SchemaValidationError("source_metadata must be an object or null", field="source_metadata")

  if "schema_version" not in data:
    raise SchemaValidationError("required field", field="schema_version")

  split_status_value = data.get("split_status", SplitStatus.UNSPLIT.value)

  return CanonicalRecord(
    schema_version=str(data["schema_version"]),
    id=str(data["id"]) if "id" in data else "",
    record_class=_parse_enum(RecordClass, data.get("record_class"), "record_class"),
    source_dataset=str(data.get("source_dataset", "")),
    source_id=data.get("source_id"),
    original_split=data.get("original_split"),
    group_id=data.get("group_id"),
    split_status=_parse_enum(SplitStatus, split_status_value, "split_status"),
    command=str(data.get("command", "")),
    scene_context=data.get("scene_context"),
    dialogue_history=list(dialogue_history),
    capability_context=data.get("capability_context"),
    candidate_interpretations=[_parse_candidate(item) for item in candidates_raw],
    ambiguity_present=data.get("ambiguity_present"),
    ambiguity_types=[_parse_enum(AmbiguityType, v, "ambiguity_types") for v in ambiguity_types_raw],
    primary_ambiguity_type=_parse_enum(
      AmbiguityType,
      data.get("primary_ambiguity_type"),
      "primary_ambiguity_type",
    )
    if data.get("primary_ambiguity_type") is not None
    else None,
    compound_ambiguity=bool(data.get("compound_ambiguity", False)),
    compound_ambiguity_count=int(data.get("compound_ambiguity_count", 0)),
    missing_slots=list(missing_slots),
    risk_relevant=bool(data.get("risk_relevant", False)),
    risk_level=_parse_enum(RiskLevel, data.get("risk_level"), "risk_level")
    if data.get("risk_level") is not None
    else None,
    capability_status=_parse_enum(CapabilityStatus, data.get("capability_status"), "capability_status")
    if data.get("capability_status") is not None
    else None,
    recommended_strategy=_parse_enum(RouteLabel, data.get("recommended_strategy"), "recommended_strategy")
    if data.get("recommended_strategy") is not None
    else None,
    strategy_sequence=[_parse_enum(RouteLabel, v, "strategy_sequence") for v in strategy_sequence_raw],
    gold_clarification_question=data.get("gold_clarification_question"),
    clarification_subtype=data.get("clarification_subtype"),
    resolved_interpretation=data.get("resolved_interpretation"),
    intent=data.get("intent"),
    slots=dict(slots),
    annotation_status=_parse_enum(AnnotationStatus, data.get("annotation_status"), "annotation_status"),
    label_confidence=_parse_enum(LabelConfidence, data.get("label_confidence"), "label_confidence"),
    label_eligibility=LabelEligibility.from_dict(label_eligibility_raw),
    mapping_version=data.get("mapping_version"),
    source_license=data.get("source_license"),
    mapping_notes=data.get("mapping_notes"),
    source_metadata=source_metadata,
  )


def canonical_record_to_dict(record: CanonicalRecord) -> dict[str, Any]:
  data = asdict(record)
  data["schema_version"] = record.schema_version
  data["record_class"] = _enum_value(record.record_class)
  data["split_status"] = _enum_value(record.split_status)
  data["annotation_status"] = _enum_value(record.annotation_status)
  data["label_confidence"] = _enum_value(record.label_confidence)
  data["ambiguity_types"] = [_enum_value(v) for v in record.ambiguity_types]
  data["primary_ambiguity_type"] = _enum_value(record.primary_ambiguity_type)
  data["risk_level"] = _enum_value(record.risk_level)
  data["capability_status"] = _enum_value(record.capability_status)
  data["recommended_strategy"] = _enum_value(record.recommended_strategy)
  data["strategy_sequence"] = [_enum_value(v) for v in record.strategy_sequence]
  data["label_eligibility"] = record.label_eligibility.to_dict()
  data["candidate_interpretations"] = [
    {
      "text": item.text,
      "confidence": item.confidence,
      "safety_status": _enum_value(item.safety_status),
    }
    for item in record.candidate_interpretations
  ]
  return data
