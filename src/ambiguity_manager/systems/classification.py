"""Ambiguity / risk / capability aggregation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ambiguity_manager.schema.v2.taxonomies import AmbiguityType, CapabilityStatus, RiskLevel
from ambiguity_manager.systems.contracts import StructuredAnalysis


@dataclass(frozen=True)
class ClassificationAggregate:
  ambiguity_present: bool
  ambiguity_types: list[str]
  compound_ambiguity: bool
  compound_ambiguity_count: int
  risk_level: str | None
  capability_status: str | None
  derivation_notes: list[str]

  def to_dict(self) -> dict[str, Any]:
    return {
      "ambiguity_present": self.ambiguity_present,
      "ambiguity_types": list(self.ambiguity_types),
      "compound_ambiguity": self.compound_ambiguity,
      "compound_ambiguity_count": self.compound_ambiguity_count,
      "risk_level": self.risk_level,
      "capability_status": self.capability_status,
      "derivation_notes": list(self.derivation_notes),
    }


def derive_ambiguity_fields(analysis: StructuredAnalysis) -> ClassificationAggregate:
  notes: list[str] = []
  types = list(analysis.ambiguity_types)
  type_values = [t.value if isinstance(t, AmbiguityType) else str(t) for t in types]
  distinct = sorted(set(type_values))
  present = bool(analysis.ambiguity_present)
  if distinct:
    present = True
    notes.append("ambiguity_present_from_types")
  elif len(analysis.candidate_interpretations) > 1 and analysis.selected_interpretation is None:
    present = True
    notes.append("ambiguity_present_from_unresolved_candidates")
  compound = len(distinct) >= 2
  compound_count = len(distinct) if compound else 0
  risk = analysis.risk_level.value if analysis.risk_level else None
  capability = analysis.capability_status.value if analysis.capability_status else None
  if risk is None:
    notes.append("risk_unknown_insufficient_evidence")
  if capability is None:
    notes.append("capability_unknown_insufficient_evidence")
  return ClassificationAggregate(
    ambiguity_present=present,
    ambiguity_types=distinct,
    compound_ambiguity=compound,
    compound_ambiguity_count=compound_count,
    risk_level=risk,
    capability_status=capability,
    derivation_notes=notes,
  )


def apply_classification_aggregate(
  analysis: StructuredAnalysis,
  aggregate: ClassificationAggregate | None = None,
) -> StructuredAnalysis:
  aggregate = aggregate or derive_ambiguity_fields(analysis)
  analysis.ambiguity_present = aggregate.ambiguity_present
  analysis.ambiguity_types = [AmbiguityType(t) for t in aggregate.ambiguity_types]
  analysis.compound_ambiguity = aggregate.compound_ambiguity
  analysis.compound_ambiguity_count = aggregate.compound_ambiguity_count
  if aggregate.ambiguity_types:
    analysis.primary_ambiguity_type = AmbiguityType(aggregate.ambiguity_types[0])
  if analysis.risk_level is None and aggregate.risk_level:
    analysis.risk_level = RiskLevel(aggregate.risk_level)
  if analysis.capability_status is None and aggregate.capability_status:
    analysis.capability_status = CapabilityStatus(aggregate.capability_status)
  # Missing risk is not "none"; treat absence as safety-relevant unknown when noted.
  if analysis.risk_level is None:
    analysis.risk_level = RiskLevel.UNKNOWN
    analysis.risk_relevant = True
    analysis.findings = list(analysis.findings) + ["risk_missing_treated_as_unknown"]
  elif analysis.risk_level == RiskLevel.UNKNOWN:
    analysis.risk_relevant = True
  else:
    analysis.risk_relevant = analysis.risk_level not in (RiskLevel.NONE,)
  if analysis.capability_status is None:
    analysis.capability_status = CapabilityStatus.UNKNOWN
    analysis.findings = list(analysis.findings) + ["capability_missing_treated_as_unknown"]
  return analysis


def escalate_risk_for_unknown_safety(
  analysis: StructuredAnalysis,
  *,
  unknown_affects_safety: bool,
) -> StructuredAnalysis:
  if unknown_affects_safety and analysis.risk_level in (None, RiskLevel.UNKNOWN):
    analysis.risk_level = RiskLevel.UNKNOWN
    analysis.risk_relevant = True
    analysis.findings = list(analysis.findings) + ["risk_escalated_unknown_affects_safety"]
  return analysis
