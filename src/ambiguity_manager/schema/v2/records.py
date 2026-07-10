"""Canonical schema v2 record dataclasses."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
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


def _enum_value(value: Any) -> Any:
  return value.value if hasattr(value, "value") else value


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
class CPCSlot:
  value: str | None = None
  status: CPCSlotStatus = CPCSlotStatus.UNKNOWN

  def to_dict(self) -> dict[str, Any]:
    return {"value": self.value, "status": _enum_value(self.status)}

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "CPCSlot":
    from ambiguity_manager.schema.v2.errors import SchemaValidationError

    if not isinstance(data, dict):
      raise SchemaValidationError("CPC slot must be an object")
    status_raw = data.get("status", CPCSlotStatus.UNKNOWN.value)
    try:
      status = CPCSlotStatus(status_raw)
    except ValueError as exc:
      raise SchemaValidationError(
        f"invalid CPC slot status {status_raw!r}",
        field="status",
      ) from exc
    value = data.get("value")
    if value is not None and not isinstance(value, str):
      raise SchemaValidationError("CPC slot value must be a string or null", field="value")
    return cls(value=value, status=status)


@dataclass
class CPC:
  action: CPCSlot = field(default_factory=CPCSlot)
  actor: CPCSlot = field(default_factory=CPCSlot)
  object: CPCSlot = field(default_factory=CPCSlot)
  object_attributes: CPCSlot = field(default_factory=CPCSlot)
  destination: CPCSlot = field(default_factory=CPCSlot)
  spatial_relation: CPCSlot = field(default_factory=CPCSlot)
  quantity: CPCSlot = field(default_factory=CPCSlot)
  time: CPCSlot = field(default_factory=CPCSlot)
  recipient: CPCSlot = field(default_factory=CPCSlot)
  tool: CPCSlot = field(default_factory=CPCSlot)
  conditions: CPCSlot = field(default_factory=CPCSlot)
  constraints: CPCSlot = field(default_factory=CPCSlot)
  negation: CPCSlot = field(default_factory=CPCSlot)

  def to_dict(self) -> dict[str, Any]:
    return {name: getattr(self, name).to_dict() for name in CPC_SLOT_NAMES}

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "CPC":
    from ambiguity_manager.schema.v2.errors import SchemaValidationError

    if not isinstance(data, dict):
      raise SchemaValidationError("cpc must be an object", field="cpc")
    slots: dict[str, CPCSlot] = {}
    for name in CPC_SLOT_NAMES:
      raw = data.get(name, {"value": None, "status": CPCSlotStatus.UNKNOWN.value})
      slots[name] = CPCSlot.from_dict(raw)
    return cls(**slots)

  @classmethod
  def empty_unknown(cls) -> "CPC":
    return cls()


@dataclass
class EvidenceRef:
  source: str
  span: str | None = None
  note: str | None = None

  def to_dict(self) -> dict[str, Any]:
    return {"source": self.source, "span": self.span, "note": self.note}

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "EvidenceRef":
    from ambiguity_manager.schema.v2.errors import SchemaValidationError

    if not isinstance(data, dict):
      raise SchemaValidationError("evidence entry must be an object")
    source = data.get("source")
    if not isinstance(source, str) or not source.strip():
      raise SchemaValidationError("evidence source is required", field="source")
    span = data.get("span")
    note = data.get("note")
    if span is not None and not isinstance(span, str):
      raise SchemaValidationError("evidence span must be a string or null", field="span")
    if note is not None and not isinstance(note, str):
      raise SchemaValidationError("evidence note must be a string or null", field="note")
    return cls(source=source, span=span, note=note)


@dataclass
class CandidateInterpretationFrame:
  frame_id: str
  text: str | None = None
  cpc: CPC = field(default_factory=CPC.empty_unknown)
  confidence: float | None = None
  safety_status: SafetyStatus | None = None

  def to_dict(self) -> dict[str, Any]:
    return {
      "frame_id": self.frame_id,
      "text": self.text,
      "cpc": self.cpc.to_dict(),
      "confidence": self.confidence,
      "safety_status": _enum_value(self.safety_status),
    }

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "CandidateInterpretationFrame":
    from ambiguity_manager.schema.v2.errors import SchemaValidationError

    if not isinstance(data, dict):
      raise SchemaValidationError("candidate frame must be an object")
    frame_id = data.get("frame_id")
    if not isinstance(frame_id, str) or not frame_id.strip():
      raise SchemaValidationError("frame_id is required", field="frame_id")
    text = data.get("text")
    if text is not None and not isinstance(text, str):
      raise SchemaValidationError("text must be a string or null", field="text")
    confidence = data.get("confidence")
    if confidence is not None and not isinstance(confidence, (int, float)):
      raise SchemaValidationError("confidence must be a number or null", field="confidence")
    safety_raw = data.get("safety_status")
    safety_status = None
    if safety_raw is not None:
      try:
        safety_status = SafetyStatus(safety_raw)
      except ValueError as exc:
        raise SchemaValidationError(
          f"invalid safety_status {safety_raw!r}",
          field="safety_status",
        ) from exc
    cpc_raw = data.get("cpc", {})
    return cls(
      frame_id=frame_id,
      text=text,
      cpc=CPC.from_dict(cpc_raw),
      confidence=float(confidence) if confidence is not None else None,
      safety_status=safety_status,
    )


@dataclass
class SelectedInterpretation:
  frame_id: str
  supporting_evidence: list[EvidenceRef] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    return {
      "frame_id": self.frame_id,
      "supporting_evidence": [item.to_dict() for item in self.supporting_evidence],
    }

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "SelectedInterpretation":
    from ambiguity_manager.schema.v2.errors import SchemaValidationError

    if not isinstance(data, dict):
      raise SchemaValidationError("selected_interpretation must be an object")
    frame_id = data.get("frame_id")
    if not isinstance(frame_id, str) or not frame_id.strip():
      raise SchemaValidationError("frame_id is required", field="frame_id")
    evidence_raw = data.get("supporting_evidence", [])
    if not isinstance(evidence_raw, list):
      raise SchemaValidationError("supporting_evidence must be a list", field="supporting_evidence")
    return cls(
      frame_id=frame_id,
      supporting_evidence=[EvidenceRef.from_dict(item) for item in evidence_raw],
    )


@dataclass
class UnresolvedSlot:
  slot_name: str
  reason: str | None = None

  def to_dict(self) -> dict[str, Any]:
    return {"slot_name": self.slot_name, "reason": self.reason}

  @classmethod
  def from_dict(cls, data: dict[str, Any] | str) -> "UnresolvedSlot":
    from ambiguity_manager.schema.v2.errors import SchemaValidationError

    if isinstance(data, str):
      return cls(slot_name=data)
    if not isinstance(data, dict):
      raise SchemaValidationError("unresolved slot must be a string or object")
    slot_name = data.get("slot_name")
    if not isinstance(slot_name, str) or not slot_name.strip():
      raise SchemaValidationError("slot_name is required", field="slot_name")
    reason = data.get("reason")
    if reason is not None and not isinstance(reason, str):
      raise SchemaValidationError("reason must be a string or null", field="reason")
    return cls(slot_name=slot_name, reason=reason)


@dataclass
class ResolvedSlotValue:
  slot_name: str
  value: str

  def to_dict(self) -> dict[str, Any]:
    return {"slot_name": self.slot_name, "value": self.value}

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "ResolvedSlotValue":
    from ambiguity_manager.schema.v2.errors import SchemaValidationError

    if not isinstance(data, dict):
      raise SchemaValidationError("resolved slot must be an object")
    slot_name = data.get("slot_name")
    value = data.get("value")
    if not isinstance(slot_name, str) or not slot_name.strip():
      raise SchemaValidationError("slot_name is required", field="slot_name")
    if not isinstance(value, str) or not value.strip():
      raise SchemaValidationError("value is required", field="value")
    return cls(slot_name=slot_name, value=value)


@dataclass
class ContextSamplingUncertainty:
  score: float | None = None
  variant_count: int | None = None
  agreement: float | None = None

  def to_dict(self) -> dict[str, Any]:
    return {
      "score": self.score,
      "variant_count": self.variant_count,
      "agreement": self.agreement,
    }

  @classmethod
  def from_dict(cls, data: dict[str, Any] | None) -> "ContextSamplingUncertainty | None":
    if data is None:
      return None
    from ambiguity_manager.schema.v2.errors import SchemaValidationError

    if not isinstance(data, dict):
      raise SchemaValidationError("context_sampling_uncertainty must be an object or null")
    score = data.get("score")
    variant_count = data.get("variant_count")
    agreement = data.get("agreement")
    if score is not None and not isinstance(score, (int, float)):
      raise SchemaValidationError("score must be a number or null", field="score")
    if variant_count is not None and not isinstance(variant_count, int):
      raise SchemaValidationError("variant_count must be an integer or null", field="variant_count")
    if agreement is not None and not isinstance(agreement, (int, float)):
      raise SchemaValidationError("agreement must be a number or null", field="agreement")
    return cls(
      score=float(score) if score is not None else None,
      variant_count=variant_count,
      agreement=float(agreement) if agreement is not None else None,
    )


@dataclass
class V1LegacyProvenance:
  missing_slots: list[str] = field(default_factory=list)
  gold_clarification_question: str | None = None
  resolved_interpretation: str | None = None
  intent: str | None = None
  slots: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    return {
      "missing_slots": list(self.missing_slots),
      "gold_clarification_question": self.gold_clarification_question,
      "resolved_interpretation": self.resolved_interpretation,
      "intent": self.intent,
      "slots": dict(self.slots),
    }

  @classmethod
  def from_dict(cls, data: dict[str, Any] | None) -> "V1LegacyProvenance | None":
    if data is None:
      return None
    from ambiguity_manager.schema.v2.errors import SchemaValidationError

    if not isinstance(data, dict):
      raise SchemaValidationError("v1_legacy must be an object or null")
    missing_slots = data.get("missing_slots", [])
    if not isinstance(missing_slots, list) or not all(isinstance(x, str) for x in missing_slots):
      raise SchemaValidationError("v1_legacy.missing_slots must be a list of strings")
    slots = data.get("slots", {})
    if not isinstance(slots, dict):
      raise SchemaValidationError("v1_legacy.slots must be an object")
    return cls(
      missing_slots=list(missing_slots),
      gold_clarification_question=data.get("gold_clarification_question"),
      resolved_interpretation=data.get("resolved_interpretation"),
      intent=data.get("intent"),
      slots=dict(slots),
    )


@dataclass
class PredictionMetadata:
  model_id: str | None = None
  prompt_hash: str | None = None
  generation_seed: int | None = None
  raw_model_output: str | None = None

  def to_dict(self) -> dict[str, Any]:
    return {
      "model_id": self.model_id,
      "prompt_hash": self.prompt_hash,
      "generation_seed": self.generation_seed,
      "raw_model_output": self.raw_model_output,
    }

  @classmethod
  def from_dict(cls, data: dict[str, Any] | None) -> "PredictionMetadata | None":
    if data is None:
      return None
    from ambiguity_manager.schema.v2.errors import SchemaValidationError

    if not isinstance(data, dict):
      raise SchemaValidationError("prediction_metadata must be an object or null")
    generation_seed = data.get("generation_seed")
    if generation_seed is not None and not isinstance(generation_seed, int):
      raise SchemaValidationError("generation_seed must be an integer or null")
    return cls(
      model_id=data.get("model_id"),
      prompt_hash=data.get("prompt_hash"),
      generation_seed=generation_seed,
      raw_model_output=data.get("raw_model_output"),
    )


@dataclass
class CanonicalRecordV2:
  id: str
  record_class: RecordClass
  source_dataset: str
  command: str
  annotation_status: AnnotationStatus
  label_confidence: LabelConfidence
  label_eligibility: LabelEligibility
  schema_version: str = SCHEMA_VERSION
  source_id: str | None = None
  original_split: str | None = None
  group_id: str | None = None
  split_status: SplitStatus = SplitStatus.UNSPLIT
  scene_context: str | None = None
  dialogue_history: list[str] = field(default_factory=list)
  capability_context: str | None = None
  speech_act: str | None = None
  intent_summary: str | None = None
  cpc: CPC = field(default_factory=CPC.empty_unknown)
  candidate_interpretations: list[CandidateInterpretationFrame] = field(default_factory=list)
  selected_interpretation: SelectedInterpretation | None = None
  unresolved_slots: list[UnresolvedSlot] = field(default_factory=list)
  supporting_evidence: list[EvidenceRef] = field(default_factory=list)
  ambiguity_present: bool | None = None
  ambiguity_types: list[AmbiguityType] = field(default_factory=list)
  primary_ambiguity_type: AmbiguityType | None = None
  compound_ambiguity: bool = False
  compound_ambiguity_count: int = 0
  risk_relevant: bool = False
  risk_level: RiskLevel | None = None
  capability_status: CapabilityStatus | None = None
  recommended_strategy: RouteLabel | None = None
  strategy_sequence: list[RouteLabel] = field(default_factory=list)
  clarification_question: str | None = None
  clarification_subtype: str | None = None
  clarification_targets: list[str] = field(default_factory=list)
  rejection_reason: str | None = None
  resolved_slots: list[ResolvedSlotValue] = field(default_factory=list)
  resolution_method: str | None = None
  resolution_evidence: list[EvidenceRef] = field(default_factory=list)
  context_sampling_uncertainty: ContextSamplingUncertainty | None = None
  migration_version: str | None = None
  migrated_from_schema_version: str | None = None
  v1_legacy: V1LegacyProvenance | None = None
  prediction_metadata: PredictionMetadata | None = None
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
    from ambiguity_manager.schema.v2.errors import SchemaValidationError

    raise SchemaValidationError(
      f"invalid value {value!r}; expected one of {[m.value for m in enum_cls]}",
      field=field_name,
    ) from exc


def canonical_record_v2_from_dict(data: dict[str, Any]) -> CanonicalRecordV2:
  from ambiguity_manager.schema.v2.errors import SchemaValidationError

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

  unresolved_raw = data.get("unresolved_slots", [])
  if not isinstance(unresolved_raw, list):
    raise SchemaValidationError("unresolved_slots must be a list", field="unresolved_slots")

  candidates_raw = data.get("candidate_interpretations", [])
  if not isinstance(candidates_raw, list):
    raise SchemaValidationError("candidate_interpretations must be a list", field="candidate_interpretations")

  clarification_targets = data.get("clarification_targets", [])
  if not isinstance(clarification_targets, list) or not all(isinstance(x, str) for x in clarification_targets):
    raise SchemaValidationError("clarification_targets must be a list of strings", field="clarification_targets")

  supporting_evidence_raw = data.get("supporting_evidence", [])
  if not isinstance(supporting_evidence_raw, list):
    raise SchemaValidationError("supporting_evidence must be a list", field="supporting_evidence")

  resolved_slots_raw = data.get("resolved_slots", [])
  if not isinstance(resolved_slots_raw, list):
    raise SchemaValidationError("resolved_slots must be a list", field="resolved_slots")

  resolution_evidence_raw = data.get("resolution_evidence", [])
  if not isinstance(resolution_evidence_raw, list):
    raise SchemaValidationError("resolution_evidence must be a list", field="resolution_evidence")

  source_metadata = data.get("source_metadata")
  if source_metadata is not None and not isinstance(source_metadata, dict):
    raise SchemaValidationError("source_metadata must be an object or null", field="source_metadata")

  if "schema_version" not in data:
    raise SchemaValidationError("required field", field="schema_version")

  split_status_value = data.get("split_status", SplitStatus.UNSPLIT.value)
  selected_raw = data.get("selected_interpretation")
  selected = SelectedInterpretation.from_dict(selected_raw) if selected_raw is not None else None

  return CanonicalRecordV2(
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
    speech_act=data.get("speech_act"),
    intent_summary=data.get("intent_summary"),
    cpc=CPC.from_dict(data.get("cpc", {})),
    candidate_interpretations=[CandidateInterpretationFrame.from_dict(item) for item in candidates_raw],
    selected_interpretation=selected,
    unresolved_slots=[UnresolvedSlot.from_dict(item) for item in unresolved_raw],
    supporting_evidence=[EvidenceRef.from_dict(item) for item in supporting_evidence_raw],
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
    clarification_question=data.get("clarification_question"),
    clarification_subtype=data.get("clarification_subtype"),
    clarification_targets=list(clarification_targets),
    rejection_reason=data.get("rejection_reason"),
    resolved_slots=[ResolvedSlotValue.from_dict(item) for item in resolved_slots_raw],
    resolution_method=data.get("resolution_method"),
    resolution_evidence=[EvidenceRef.from_dict(item) for item in resolution_evidence_raw],
    context_sampling_uncertainty=ContextSamplingUncertainty.from_dict(
      data.get("context_sampling_uncertainty")
    ),
    migration_version=data.get("migration_version"),
    migrated_from_schema_version=data.get("migrated_from_schema_version"),
    v1_legacy=V1LegacyProvenance.from_dict(data.get("v1_legacy")),
    prediction_metadata=PredictionMetadata.from_dict(data.get("prediction_metadata")),
    annotation_status=_parse_enum(AnnotationStatus, data.get("annotation_status"), "annotation_status"),
    label_confidence=_parse_enum(LabelConfidence, data.get("label_confidence"), "label_confidence"),
    label_eligibility=LabelEligibility.from_dict(label_eligibility_raw),
    mapping_version=data.get("mapping_version"),
    source_license=data.get("source_license"),
    mapping_notes=data.get("mapping_notes"),
    source_metadata=source_metadata,
  )


def canonical_record_v2_to_dict(record: CanonicalRecordV2) -> dict[str, Any]:
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
  data["cpc"] = record.cpc.to_dict()
  data["candidate_interpretations"] = [item.to_dict() for item in record.candidate_interpretations]
  data["selected_interpretation"] = (
    record.selected_interpretation.to_dict() if record.selected_interpretation is not None else None
  )
  data["unresolved_slots"] = [item.to_dict() for item in record.unresolved_slots]
  data["supporting_evidence"] = [item.to_dict() for item in record.supporting_evidence]
  data["resolved_slots"] = [item.to_dict() for item in record.resolved_slots]
  data["resolution_evidence"] = [item.to_dict() for item in record.resolution_evidence]
  data["context_sampling_uncertainty"] = (
    record.context_sampling_uncertainty.to_dict()
    if record.context_sampling_uncertainty is not None
    else None
  )
  data["v1_legacy"] = record.v1_legacy.to_dict() if record.v1_legacy is not None else None
  data["prediction_metadata"] = (
    record.prediction_metadata.to_dict() if record.prediction_metadata is not None else None
  )
  return data
