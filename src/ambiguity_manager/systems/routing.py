"""Deterministic type/risk/capability-aware router."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema.v2.taxonomies import (
  AmbiguityType,
  CapabilityStatus,
  RiskLevel,
  RouteLabel,
)
from ambiguity_manager.systems.candidate_generation import CRITICAL_SLOTS
from ambiguity_manager.systems.contracts import StructuredAnalysis
from ambiguity_manager.systems.errors import SystemsContractError


def load_route_precedence(path: Path | None = None) -> dict[str, Any]:
  if path is None:
    path = ProjectPaths.from_repo_root().configs / "annotation" / "route_precedence_v1.json"
  return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class RouterDecision:
  recommended_strategy: RouteLabel
  strategy_sequence: list[RouteLabel]
  matched_rule_id: str
  considered_rules: list[str]
  clarification_targets: list[str] = field(default_factory=list)
  rejection_reason: str | None = None
  notes: list[str] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    return {
      "recommended_strategy": self.recommended_strategy.value,
      "strategy_sequence": [s.value for s in self.strategy_sequence],
      "matched_rule_id": self.matched_rule_id,
      "considered_rules": list(self.considered_rules),
      "clarification_targets": list(self.clarification_targets),
      "rejection_reason": self.rejection_reason,
      "notes": list(self.notes),
    }


def _unresolved_critical(analysis: StructuredAnalysis) -> list[str]:
  return [u.slot_name for u in analysis.unresolved_slots if u.slot_name in CRITICAL_SLOTS]


def _clarification_targets(analysis: StructuredAnalysis) -> list[str]:
  targets = [u.slot_name for u in analysis.unresolved_slots]
  if not targets and analysis.ambiguity_types:
    targets = [t.value if isinstance(t, AmbiguityType) else str(t) for t in analysis.ambiguity_types]
  # unique preserve order
  seen: set[str] = set()
  ordered: list[str] = []
  for item in targets:
    if item not in seen:
      seen.add(item)
      ordered.append(item)
  return ordered


def _has_hazard_identity_ambiguity(analysis: StructuredAnalysis) -> bool:
  types = {
    t.value if isinstance(t, AmbiguityType) else str(t) for t in analysis.ambiguity_types
  }
  return "referential" in types and "safety_precondition" in types


def _is_prohibited(analysis: StructuredAnalysis) -> bool:
  if analysis.speech_act == "prohibition":
    return True
  findings = " ".join(analysis.findings).lower()
  return "prohibited" in findings or "unsafe_action" in findings


def _dependent_compound(analysis: StructuredAnalysis) -> bool:
  types = {
    t.value if isinstance(t, AmbiguityType) else str(t) for t in analysis.ambiguity_types
  }
  return len(types) >= 2 and bool(_unresolved_critical(analysis))


class DeterministicRouter:
  def __init__(self, precedence: dict[str, Any] | None = None) -> None:
    self.precedence = precedence or load_route_precedence()

  def route(self, analysis: StructuredAnalysis) -> RouterDecision:
    considered: list[str] = []
    unresolved = _unresolved_critical(analysis)
    risk = analysis.risk_level
    capability = analysis.capability_status
    targets = _clarification_targets(analysis)
    notes: list[str] = []

    # Rank 1 — known unsafe/prohibited, unless hazard identity needs clarify first
    considered.append("known_unsafe_or_prohibited")
    if _is_prohibited(analysis) or (
      risk == RiskLevel.HIGH and "unsafe" in " ".join(analysis.findings).lower()
    ):
      if _has_hazard_identity_ambiguity(analysis) and unresolved:
        considered.append("hazard_identity_unresolved")
        return RouterDecision(
          recommended_strategy=RouteLabel.CLARIFY,
          strategy_sequence=[],
          matched_rule_id="hazard_identity_unresolved",
          considered_rules=considered,
          clarification_targets=targets or unresolved,
          notes=["clarify_before_reject_for_hazard_identity"],
        )
      return RouterDecision(
        recommended_strategy=RouteLabel.FACE_PRESERVING_REJECTION,
        strategy_sequence=[],
        matched_rule_id="known_unsafe_or_prohibited",
        considered_rules=considered,
        rejection_reason="unsafe_or_prohibited_action",
      )

    # Rank 2 — known incapable
    considered.append("known_incapable")
    if capability == CapabilityStatus.INCAPABLE:
      if unresolved and "capability" in {
        t.value if isinstance(t, AmbiguityType) else str(t) for t in analysis.ambiguity_types
      }:
        return RouterDecision(
          recommended_strategy=RouteLabel.CLARIFY,
          strategy_sequence=[],
          matched_rule_id="capability_identity_unresolved",
          considered_rules=considered,
          clarification_targets=targets or unresolved,
          notes=["clarify_which_capability_applies"],
        )
      return RouterDecision(
        recommended_strategy=RouteLabel.FACE_PRESERVING_REJECTION,
        strategy_sequence=[],
        matched_rule_id="known_incapable",
        considered_rules=considered,
        rejection_reason="known_incapability",
      )

    # Rank 3 — hazard identity unresolved (single-decision clarify-before-reject)
    considered.append("hazard_identity_unresolved")
    if _has_hazard_identity_ambiguity(analysis) and unresolved and not _dependent_compound(analysis):
      return RouterDecision(
        recommended_strategy=RouteLabel.CLARIFY,
        strategy_sequence=[],
        matched_rule_id="hazard_identity_unresolved",
        considered_rules=considered,
        clarification_targets=targets or unresolved,
      )

    # Rank 4 — critical unresolved medium/high risk
    considered.append("critical_unresolved_medium_high_risk")
    if unresolved and risk in (RiskLevel.MEDIUM, RiskLevel.HIGH):
      if _dependent_compound(analysis):
        sequence = [RouteLabel.CLARIFY, RouteLabel.EXECUTE]
        return RouterDecision(
          recommended_strategy=RouteLabel.MULTI_STEP,
          strategy_sequence=sequence,
          matched_rule_id="critical_unresolved_medium_high_risk",
          considered_rules=considered,
          clarification_targets=targets or unresolved,
          notes=["never_silently_resolve_medium_high_risk"],
        )
      return RouterDecision(
        recommended_strategy=RouteLabel.CLARIFY,
        strategy_sequence=[],
        matched_rule_id="critical_unresolved_medium_high_risk",
        considered_rules=considered,
        clarification_targets=targets or unresolved,
        notes=["never_silently_resolve_medium_high_risk"],
      )

    # Unknown risk affecting safety
    if risk == RiskLevel.UNKNOWN and (analysis.risk_relevant or unresolved):
      considered.append("unknown_safety_risk")
      if _dependent_compound(analysis):
        return RouterDecision(
          recommended_strategy=RouteLabel.MULTI_STEP,
          strategy_sequence=[RouteLabel.CLARIFY, RouteLabel.EXECUTE],
          matched_rule_id="unknown_safety_risk",
          considered_rules=considered,
          clarification_targets=targets or unresolved,
        )
      return RouterDecision(
        recommended_strategy=RouteLabel.CLARIFY,
        strategy_sequence=[],
        matched_rule_id="unknown_safety_risk",
        considered_rules=considered,
        clarification_targets=targets or unresolved,
      )

    # Rank 5 — dependent compound
    considered.append("dependent_compound_ambiguities")
    if _dependent_compound(analysis):
      return RouterDecision(
        recommended_strategy=RouteLabel.MULTI_STEP,
        strategy_sequence=[RouteLabel.CLARIFY, RouteLabel.SILENTLY_RESOLVE],
        matched_rule_id="dependent_compound_ambiguities",
        considered_rules=considered,
        clarification_targets=targets or unresolved,
      )

    # Rank 6 — unique low-risk resolvable
    considered.append("unique_low_risk_resolvable")
    if (
      analysis.resolved_slots
      and risk in (None, RiskLevel.NONE, RiskLevel.LOW)
      and not unresolved
      and (analysis.ambiguity_present or analysis.ambiguity_types)
    ):
      return RouterDecision(
        recommended_strategy=RouteLabel.SILENTLY_RESOLVE,
        strategy_sequence=[],
        matched_rule_id="unique_low_risk_resolvable",
        considered_rules=considered,
        notes=["requires_resolved_slots"],
      )

    # Rank 7 — clear safe capable
    considered.append("clear_safe_capable")
    if (
      not unresolved
      and not analysis.ambiguity_present
      and not analysis.ambiguity_types
      and risk in (None, RiskLevel.NONE, RiskLevel.LOW)
      and capability in (None, CapabilityStatus.CAPABLE, CapabilityStatus.CONDITIONAL)
    ):
      return RouterDecision(
        recommended_strategy=RouteLabel.EXECUTE,
        strategy_sequence=[],
        matched_rule_id="clear_safe_capable",
        considered_rules=considered,
      )

    # Rank 8 — default clarify
    considered.append("default_clarify")
    return RouterDecision(
      recommended_strategy=RouteLabel.CLARIFY,
      strategy_sequence=[],
      matched_rule_id="default_clarify",
      considered_rules=considered,
      clarification_targets=targets or unresolved or ["intent"],
      notes=notes or ["default_clarify_no_unsupported_specificity"],
    )

  def validate_decision(self, decision: RouterDecision, analysis: StructuredAnalysis) -> None:
    strategy = decision.recommended_strategy
    if strategy == RouteLabel.SILENTLY_RESOLVE and not analysis.resolved_slots and not decision.notes:
      # caller must supply resolved slots on analysis
      if not analysis.resolved_slots:
        raise SystemsContractError("silently_resolve requires resolved slot values")
    if strategy == RouteLabel.EXECUTE and _unresolved_critical(analysis):
      raise SystemsContractError("execute blocked with unresolved critical safety slots")
    if strategy == RouteLabel.MULTI_STEP and len(decision.strategy_sequence) < 2:
      raise SystemsContractError("multi_step requires strategy_sequence length >= 2")
    if strategy == RouteLabel.CLARIFY and not decision.clarification_targets:
      raise SystemsContractError("clarify requires clarification targets")
    if strategy == RouteLabel.FACE_PRESERVING_REJECTION and not decision.rejection_reason:
      raise SystemsContractError("rejection requires a rejection reason")
    # refuse impossible sequences
    if RouteLabel.SILENTLY_RESOLVE in decision.strategy_sequence:
      if analysis.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH) and _unresolved_critical(analysis):
        raise SystemsContractError("impossible strategy sequence: silent resolve under unresolved medium/high risk")


def apply_router_decision(analysis: StructuredAnalysis, decision: RouterDecision) -> StructuredAnalysis:
  analysis.recommended_strategy = decision.recommended_strategy
  analysis.strategy_sequence = list(decision.strategy_sequence)
  analysis.clarification_targets = list(decision.clarification_targets)
  analysis.rejection_reason = decision.rejection_reason
  return analysis
