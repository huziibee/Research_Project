"""Immutable shared contracts for manager/system execution."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from ambiguity_manager.schema.v2.records import (
  CPC,
  CandidateInterpretationFrame,
  ContextSamplingUncertainty,
  EvidenceRef,
  LabelEligibility,
  ResolvedSlotValue,
  SelectedInterpretation,
  UnresolvedSlot,
)
from ambiguity_manager.schema.v2.taxonomies import (
  AmbiguityType,
  CapabilityStatus,
  RiskLevel,
  RouteLabel,
)
from ambiguity_manager.schema.v2.version import SCHEMA_VERSION
from ambiguity_manager.systems.errors import SystemsContractError
from ambiguity_manager.systems.hashing import sha256_json

INTENT_LABELS: frozenset[str] = frozenset(
  {
    "directive_command",
    "indirect_request",
    "information_question",
    "permission_request",
    "prohibition",
    "conditional_directive",
    "multi_intent",
    "other_non_actionable",
  }
)

EXECUTION_STATUSES: frozenset[str] = frozenset(
  {
    "ok",
    "rejected_by_safety",
    "not_executable",
    "provider_unavailable",
    "failed",
    "skipped",
  }
)


def _enum_value(value: Any) -> Any:
  return value.value if hasattr(value, "value") else value


def _require_str(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
  if not isinstance(value, str):
    raise SystemsContractError(f"{field_name} must be a string")
  if not allow_empty and not value.strip():
    raise SystemsContractError(f"{field_name} must be non-empty")
  return value


@dataclass(frozen=True)
class InputProvenance:
  source: str
  source_dataset: str | None = None
  source_id: str | None = None
  notes: str | None = None

  def to_dict(self) -> dict[str, Any]:
    return {
      "source": self.source,
      "source_dataset": self.source_dataset,
      "source_id": self.source_id,
      "notes": self.notes,
    }

  @classmethod
  def from_dict(cls, data: dict[str, Any] | None) -> "InputProvenance":
    if data is None:
      return cls(source="unspecified")
    if not isinstance(data, dict):
      raise SystemsContractError("input_provenance must be an object")
    source = _require_str(data.get("source", "unspecified"), "input_provenance.source")
    return cls(
      source=source,
      source_dataset=data.get("source_dataset"),
      source_id=data.get("source_id"),
      notes=data.get("notes"),
    )


@dataclass(frozen=True)
class SystemInput:
  record_id: str
  command: str
  dialogue_history: tuple[str, ...] = ()
  scene_context: str | None = None
  capability_context: str | None = None
  input_provenance: InputProvenance = field(default_factory=lambda: InputProvenance(source="unspecified"))
  schema_version: str = SCHEMA_VERSION
  label_eligibility: LabelEligibility | None = None
  protected_data: bool = False
  cached_analysis_id: str | None = None
  extra: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    payload: dict[str, Any] = {
      "record_id": self.record_id,
      "command": self.command,
      "dialogue_history": list(self.dialogue_history),
      "scene_context": self.scene_context,
      "capability_context": self.capability_context,
      "input_provenance": self.input_provenance.to_dict(),
      "schema_version": self.schema_version,
      "protected_data": self.protected_data,
      "cached_analysis_id": self.cached_analysis_id,
    }
    if self.label_eligibility is not None:
      payload["label_eligibility"] = self.label_eligibility.to_dict()
    if self.extra:
      payload["extra"] = copy.deepcopy(self.extra)
    return payload

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "SystemInput":
    if not isinstance(data, dict):
      raise SystemsContractError("SystemInput must be an object")
    record_id = _require_str(data.get("record_id"), "record_id")
    command = _require_str(data.get("command"), "command")
    history = data.get("dialogue_history", [])
    if not isinstance(history, list) or not all(isinstance(x, str) for x in history):
      raise SystemsContractError("dialogue_history must be a list of strings")
    eligibility = None
    if "label_eligibility" in data and data["label_eligibility"] is not None:
      eligibility = LabelEligibility.from_dict(data["label_eligibility"])
    scene = data.get("scene_context")
    capability = data.get("capability_context")
    if scene is not None and not isinstance(scene, str):
      raise SystemsContractError("scene_context must be a string or null")
    if capability is not None and not isinstance(capability, str):
      raise SystemsContractError("capability_context must be a string or null")
    extra = data.get("extra", {})
    if extra is None:
      extra = {}
    if not isinstance(extra, dict):
      raise SystemsContractError("extra must be an object")
    return cls(
      record_id=record_id,
      command=command,
      dialogue_history=tuple(history),
      scene_context=scene,
      capability_context=capability,
      input_provenance=InputProvenance.from_dict(data.get("input_provenance")),
      schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
      label_eligibility=eligibility,
      protected_data=bool(data.get("protected_data", False)),
      cached_analysis_id=data.get("cached_analysis_id"),
      extra=copy.deepcopy(extra),
    )

  def fingerprint(self) -> str:
    return sha256_json(self.to_dict())

  def without_context(self) -> "SystemInput":
    """Return a copy with dialogue/scene/capability context removed."""
    return SystemInput(
      record_id=self.record_id,
      command=self.command,
      dialogue_history=(),
      scene_context=None,
      capability_context=None,
      input_provenance=self.input_provenance,
      schema_version=self.schema_version,
      label_eligibility=self.label_eligibility,
      protected_data=self.protected_data,
      cached_analysis_id=self.cached_analysis_id,
      extra={
        **copy.deepcopy(self.extra),
        "context_ablation": {
          "dialogue_history_removed": True,
          "scene_context_removed": True,
          "capability_context_removed": True,
        },
      },
    )

  def fingerprint(self) -> str:
    """Canonical content hash of the full SystemInput (no volatile timestamps)."""
    return sha256_json(self.to_dict())


@dataclass
class AnalysisProvenance:
  provider_id: str | None = None
  provider_version: str | None = None
  analysis_id: str | None = None
  method: str = "deterministic"
  notes: str | None = None

  def to_dict(self) -> dict[str, Any]:
    return {
      "provider_id": self.provider_id,
      "provider_version": self.provider_version,
      "analysis_id": self.analysis_id,
      "method": self.method,
      "notes": self.notes,
    }

  @classmethod
  def from_dict(cls, data: dict[str, Any] | None) -> "AnalysisProvenance":
    if data is None:
      return cls()
    if not isinstance(data, dict):
      raise SystemsContractError("analysis_provenance must be an object")
    return cls(
      provider_id=data.get("provider_id"),
      provider_version=data.get("provider_version"),
      analysis_id=data.get("analysis_id"),
      method=str(data.get("method", "deterministic")),
      notes=data.get("notes"),
    )


@dataclass
class StructuredAnalysis:
  speech_act: str | None = None
  intent_summary: str | None = None
  cpc: CPC = field(default_factory=CPC.empty_unknown)
  candidate_interpretations: list[CandidateInterpretationFrame] = field(default_factory=list)
  selected_interpretation: SelectedInterpretation | None = None
  unresolved_slots: list[UnresolvedSlot] = field(default_factory=list)
  resolved_slots: list[ResolvedSlotValue] = field(default_factory=list)
  supporting_evidence: list[EvidenceRef] = field(default_factory=list)
  ambiguity_present: bool | None = None
  ambiguity_types: list[AmbiguityType] = field(default_factory=list)
  primary_ambiguity_type: AmbiguityType | None = None
  compound_ambiguity: bool = False
  compound_ambiguity_count: int = 0
  risk_relevant: bool = False
  risk_level: RiskLevel | None = None
  capability_status: CapabilityStatus | None = None
  context_sampling_uncertainty: ContextSamplingUncertainty | None = None
  recommended_strategy: RouteLabel | None = None
  strategy_sequence: list[RouteLabel] = field(default_factory=list)
  clarification_targets: list[str] = field(default_factory=list)
  clarification_question: str | None = None
  rejection_reason: str | None = None
  resolution_method: str | None = None
  resolution_evidence: list[EvidenceRef] = field(default_factory=list)
  analysis_provenance: AnalysisProvenance = field(default_factory=AnalysisProvenance)
  unsupported_specificity: list[str] = field(default_factory=list)
  findings: list[str] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    return {
      "speech_act": self.speech_act,
      "intent_summary": self.intent_summary,
      "cpc": self.cpc.to_dict(),
      "candidate_interpretations": [c.to_dict() for c in self.candidate_interpretations],
      "selected_interpretation": (
        self.selected_interpretation.to_dict() if self.selected_interpretation else None
      ),
      "unresolved_slots": [u.to_dict() for u in self.unresolved_slots],
      "resolved_slots": [r.to_dict() for r in self.resolved_slots],
      "supporting_evidence": [e.to_dict() for e in self.supporting_evidence],
      "ambiguity_present": self.ambiguity_present,
      "ambiguity_types": [_enum_value(t) for t in self.ambiguity_types],
      "primary_ambiguity_type": _enum_value(self.primary_ambiguity_type),
      "compound_ambiguity": self.compound_ambiguity,
      "compound_ambiguity_count": self.compound_ambiguity_count,
      "risk_relevant": self.risk_relevant,
      "risk_level": _enum_value(self.risk_level),
      "capability_status": _enum_value(self.capability_status),
      "context_sampling_uncertainty": (
        self.context_sampling_uncertainty.to_dict()
        if self.context_sampling_uncertainty
        else None
      ),
      "recommended_strategy": _enum_value(self.recommended_strategy),
      "strategy_sequence": [_enum_value(s) for s in self.strategy_sequence],
      "clarification_targets": list(self.clarification_targets),
      "clarification_question": self.clarification_question,
      "rejection_reason": self.rejection_reason,
      "resolution_method": self.resolution_method,
      "resolution_evidence": [e.to_dict() for e in self.resolution_evidence],
      "analysis_provenance": self.analysis_provenance.to_dict(),
      "unsupported_specificity": list(self.unsupported_specificity),
      "findings": list(self.findings),
    }

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "StructuredAnalysis":
    if not isinstance(data, dict):
      raise SystemsContractError("StructuredAnalysis must be an object")
    speech_act = data.get("speech_act")
    if speech_act is not None:
      if not isinstance(speech_act, str):
        raise SystemsContractError("speech_act must be a string or null")
      if speech_act not in INTENT_LABELS:
        raise SystemsContractError(f"invalid speech_act {speech_act!r}")
    ambiguity_types: list[AmbiguityType] = []
    for raw in data.get("ambiguity_types", []) or []:
      try:
        ambiguity_types.append(AmbiguityType(raw))
      except ValueError as exc:
        raise SystemsContractError(f"invalid ambiguity type {raw!r}") from exc
    primary = data.get("primary_ambiguity_type")
    primary_type = None
    if primary is not None:
      try:
        primary_type = AmbiguityType(primary)
      except ValueError as exc:
        raise SystemsContractError(f"invalid primary_ambiguity_type {primary!r}") from exc
    risk = data.get("risk_level")
    risk_level = None
    if risk is not None:
      try:
        risk_level = RiskLevel(risk)
      except ValueError as exc:
        raise SystemsContractError(f"invalid risk_level {risk!r}") from exc
    capability = data.get("capability_status")
    capability_status = None
    if capability is not None:
      try:
        capability_status = CapabilityStatus(capability)
      except ValueError as exc:
        raise SystemsContractError(f"invalid capability_status {capability!r}") from exc
    route = data.get("recommended_strategy")
    recommended = None
    if route is not None:
      try:
        recommended = RouteLabel(route)
      except ValueError as exc:
        raise SystemsContractError(f"invalid recommended_strategy {route!r}") from exc
    sequence: list[RouteLabel] = []
    for raw in data.get("strategy_sequence", []) or []:
      try:
        sequence.append(RouteLabel(raw))
      except ValueError as exc:
        raise SystemsContractError(f"invalid strategy_sequence value {raw!r}") from exc
    selected_raw = data.get("selected_interpretation")
    selected = (
      SelectedInterpretation.from_dict(selected_raw) if selected_raw is not None else None
    )
    uncertainty_raw = data.get("context_sampling_uncertainty")
    return cls(
      speech_act=speech_act,
      intent_summary=data.get("intent_summary"),
      cpc=CPC.from_dict(data.get("cpc", {})),
      candidate_interpretations=[
        CandidateInterpretationFrame.from_dict(item)
        for item in data.get("candidate_interpretations", []) or []
      ],
      selected_interpretation=selected,
      unresolved_slots=[
        UnresolvedSlot.from_dict(item) for item in data.get("unresolved_slots", []) or []
      ],
      resolved_slots=[
        ResolvedSlotValue.from_dict(item) for item in data.get("resolved_slots", []) or []
      ],
      supporting_evidence=[
        EvidenceRef.from_dict(item) for item in data.get("supporting_evidence", []) or []
      ],
      ambiguity_present=data.get("ambiguity_present"),
      ambiguity_types=ambiguity_types,
      primary_ambiguity_type=primary_type,
      compound_ambiguity=bool(data.get("compound_ambiguity", False)),
      compound_ambiguity_count=int(data.get("compound_ambiguity_count", 0) or 0),
      risk_relevant=bool(data.get("risk_relevant", False)),
      risk_level=risk_level,
      capability_status=capability_status,
      context_sampling_uncertainty=ContextSamplingUncertainty.from_dict(uncertainty_raw),
      recommended_strategy=recommended,
      strategy_sequence=sequence,
      clarification_targets=list(data.get("clarification_targets", []) or []),
      clarification_question=data.get("clarification_question"),
      rejection_reason=data.get("rejection_reason"),
      resolution_method=data.get("resolution_method"),
      resolution_evidence=[
        EvidenceRef.from_dict(item) for item in data.get("resolution_evidence", []) or []
      ],
      analysis_provenance=AnalysisProvenance.from_dict(data.get("analysis_provenance")),
      unsupported_specificity=list(data.get("unsupported_specificity", []) or []),
      findings=list(data.get("findings", []) or []),
    )

  def fingerprint(self) -> str:
    return sha256_json(self.to_dict())


@dataclass
class SafetyFinding:
  finding_type: str
  message: str
  severity: str = "error"
  slot: str | None = None
  details: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    return {
      "finding_type": self.finding_type,
      "message": self.message,
      "severity": self.severity,
      "slot": self.slot,
      "details": copy.deepcopy(self.details),
    }

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "SafetyFinding":
    if not isinstance(data, dict):
      raise SystemsContractError("SafetyFinding must be an object")
    finding_type = _require_str(data.get("finding_type"), "finding_type")
    message = _require_str(data.get("message"), "message")
    return cls(
      finding_type=finding_type,
      message=message,
      severity=str(data.get("severity", "error")),
      slot=data.get("slot"),
      details=copy.deepcopy(data.get("details", {}) or {}),
    )


@dataclass
class SystemResult:
  record_id: str
  system_id: str
  system_version: str
  analysis: StructuredAnalysis
  recommended_strategy: RouteLabel | None
  strategy_sequence: list[RouteLabel] = field(default_factory=list)
  clarification_targets: list[str] = field(default_factory=list)
  clarification_question: str | None = None
  resolved_slots: list[ResolvedSlotValue] = field(default_factory=list)
  rejection_reason: str | None = None
  unsupported_commitment_findings: list[SafetyFinding] = field(default_factory=list)
  safety_findings: list[SafetyFinding] = field(default_factory=list)
  execution_status: str = "ok"
  provider_provenance: dict[str, Any] = field(default_factory=dict)
  runtime_metadata: dict[str, Any] = field(default_factory=dict)
  result_hash: str | None = None
  synthetic_only: bool = True
  official_result: bool = False
  run_mode: str | None = None
  run_id: str | None = None

  def to_dict(self) -> dict[str, Any]:
    payload = {
      "record_id": self.record_id,
      "system_id": self.system_id,
      "system_version": self.system_version,
      "analysis": self.analysis.to_dict(),
      "recommended_strategy": _enum_value(self.recommended_strategy),
      "strategy_sequence": [_enum_value(s) for s in self.strategy_sequence],
      "clarification_targets": list(self.clarification_targets),
      "clarification_question": self.clarification_question,
      "resolved_slots": [r.to_dict() for r in self.resolved_slots],
      "rejection_reason": self.rejection_reason,
      "unsupported_commitment_findings": [
        f.to_dict() for f in self.unsupported_commitment_findings
      ],
      "safety_findings": [f.to_dict() for f in self.safety_findings],
      "execution_status": self.execution_status,
      "provider_provenance": copy.deepcopy(self.provider_provenance),
      "runtime_metadata": copy.deepcopy(self.runtime_metadata),
      "synthetic_only": self.synthetic_only,
      "official_result": self.official_result,
      "run_mode": self.run_mode,
      "run_id": self.run_id,
    }
    payload["result_hash"] = self.result_hash or sha256_json(
      {k: v for k, v in payload.items() if k != "result_hash"}
    )
    return payload

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "SystemResult":
    if not isinstance(data, dict):
      raise SystemsContractError("SystemResult must be an object")
    record_id = _require_str(data.get("record_id"), "record_id")
    system_id = _require_str(data.get("system_id"), "system_id")
    system_version = _require_str(data.get("system_version"), "system_version")
    status = data.get("execution_status", "ok")
    if status not in EXECUTION_STATUSES:
      raise SystemsContractError(f"invalid execution_status {status!r}")
    route = data.get("recommended_strategy")
    recommended = None
    if route is not None:
      try:
        recommended = RouteLabel(route)
      except ValueError as exc:
        raise SystemsContractError(f"invalid recommended_strategy {route!r}") from exc
    sequence: list[RouteLabel] = []
    for raw in data.get("strategy_sequence", []) or []:
      try:
        sequence.append(RouteLabel(raw))
      except ValueError as exc:
        raise SystemsContractError(f"invalid strategy_sequence value {raw!r}") from exc
    analysis = StructuredAnalysis.from_dict(data.get("analysis") or {})
    result = cls(
      record_id=record_id,
      system_id=system_id,
      system_version=system_version,
      analysis=analysis,
      recommended_strategy=recommended,
      strategy_sequence=sequence,
      clarification_targets=list(data.get("clarification_targets", []) or []),
      clarification_question=data.get("clarification_question"),
      resolved_slots=[
        ResolvedSlotValue.from_dict(item) for item in data.get("resolved_slots", []) or []
      ],
      rejection_reason=data.get("rejection_reason"),
      unsupported_commitment_findings=[
        SafetyFinding.from_dict(item)
        for item in data.get("unsupported_commitment_findings", []) or []
      ],
      safety_findings=[
        SafetyFinding.from_dict(item) for item in data.get("safety_findings", []) or []
      ],
      execution_status=str(status),
      provider_provenance=copy.deepcopy(data.get("provider_provenance", {}) or {}),
      runtime_metadata=copy.deepcopy(data.get("runtime_metadata", {}) or {}),
      result_hash=data.get("result_hash"),
      synthetic_only=bool(data.get("synthetic_only", True)),
      official_result=bool(data.get("official_result", False)),
      run_mode=data.get("run_mode"),
      run_id=data.get("run_id"),
    )
    if result.result_hash is None:
      result.result_hash = result.compute_hash()
    return result

  def compute_hash(self) -> str:
    payload = self.to_dict()
    payload.pop("result_hash", None)
    return sha256_json(payload)

  def with_computed_hash(self) -> "SystemResult":
    self.result_hash = self.compute_hash()
    return self
