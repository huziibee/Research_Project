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
  requires_re_evaluation: bool = False

  def to_dict(self) -> dict[str, Any]:
    return {
      "recommended_strategy": self.recommended_strategy.value,
      "strategy_sequence": [s.value for s in self.strategy_sequence],
      "matched_rule_id": self.matched_rule_id,
      "considered_rules": list(self.considered_rules),
      "clarification_targets": list(self.clarification_targets),
      "rejection_reason": self.rejection_reason,
      "notes": list(self.notes),
      "requires_re_evaluation": self.requires_re_evaluation,
    }


def _unresolved_critical(analysis: StructuredAnalysis) -> list[str]:
  return [u.slot_name for u in analysis.unresolved_slots if u.slot_name in CRITICAL_SLOTS]


def _clarification_targets(analysis: StructuredAnalysis) -> list[str]:
  targets = [u.slot_name for u in analysis.unresolved_slots]
  if not targets and analysis.ambiguity_types:
    targets = [t.value if isinstance(t, AmbiguityType) else str(t) for t in analysis.ambiguity_types]
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
  """Reject only when the requested action itself is unsafe/prohibited — not speech_act alone."""
  findings = " ".join(analysis.findings).lower()
  return "prohibited" in findings or "unsafe_action" in findings


def _dependent_compound(analysis: StructuredAnalysis) -> bool:
  types = {
    t.value if isinstance(t, AmbiguityType) else str(t) for t in analysis.ambiguity_types
  }
  return len(types) >= 2 and bool(_unresolved_critical(analysis))


def _conditions_verified(analysis: StructuredAnalysis) -> bool:
  blob = " ".join(analysis.findings).lower()
  if "conditions_verified" in blob or "conditional_capability_verified" in blob:
    return True
  if any(
    (e.note or "").lower() in {"conditions_verified", "conditional_capability_verified"}
    for e in analysis.supporting_evidence
  ):
    return True
  return False


def _effective_risk(analysis: StructuredAnalysis) -> RiskLevel | None:
  """Missing safety-relevant evidence becomes unknown; explicit NONE remains NONE."""
  if analysis.risk_level is not None:
    return analysis.risk_level
  # Absent risk with unresolved critical / ambiguity / findings → unknown.
  if analysis.risk_relevant or _unresolved_critical(analysis) or analysis.ambiguity_types:
    return RiskLevel.UNKNOWN
  # Truly clear absences stay None and are not treated as safe for execute.
  return None


def _effective_capability(analysis: StructuredAnalysis) -> CapabilityStatus | None:
  if analysis.capability_status is not None:
    return analysis.capability_status
  return None


def _multi_step_clarify_only(
  *,
  matched_rule_id: str,
  considered: list[str],
  targets: list[str],
  notes: list[str] | None = None,
) -> RouterDecision:
  """MULTI_STEP without precommitting to execute; re-evaluation is mandatory."""
  return RouterDecision(
    recommended_strategy=RouteLabel.MULTI_STEP,
    strategy_sequence=[RouteLabel.CLARIFY],
    matched_rule_id=matched_rule_id,
    considered_rules=considered,
    clarification_targets=targets,
    notes=list(notes or []) + ["requires_re_evaluation", "no_precommit_execute"],
    requires_re_evaluation=True,
  )


POLICY_T39_CONSERVATIVE = "t39_conservative"
POLICY_GOAL_FIRST_V1 = "goal_first_v1"
POLICY_GOAL_FIRST_V2 = "goal_first_v2"
POLICY_GOAL_FIRST_V2_GOAL_LICENSED = "goal_first_v2_goal_licensed"
_ACTIONABLE_SPEECH_ACTS = frozenset(
  {
    "directive_command",
    "indirect_request",
    "conditional_directive",
    "permission_request",
  }
)
_QUESTION_SHAPED_ACTS = frozenset({"information_question", "other_non_actionable"})
_KNOWN_POLICIES = {
  POLICY_T39_CONSERVATIVE,
  POLICY_GOAL_FIRST_V1,
  POLICY_GOAL_FIRST_V2,
  POLICY_GOAL_FIRST_V2_GOAL_LICENSED,
}


def _pilot_capability_label(analysis: StructuredAnalysis) -> str | None:
  for finding in analysis.findings:
    text = str(finding)
    if text.startswith("pilot_capability_status:"):
      return text.split(":", 1)[1].strip()
  return None


class DeterministicRouter:
  def __init__(
    self,
    precedence: dict[str, Any] | None = None,
    *,
    policy: str = POLICY_T39_CONSERVATIVE,
  ) -> None:
    if policy not in _KNOWN_POLICIES:
      raise SystemsContractError(f"unknown_router_policy:{policy}")
    self.precedence = precedence or load_route_precedence()
    self.policy = policy

  def route(self, analysis: StructuredAnalysis) -> RouterDecision:
    if self.policy == POLICY_GOAL_FIRST_V1:
      return self._route_goal_first(analysis)
    if self.policy == POLICY_GOAL_FIRST_V2:
      return self._route_goal_first_v2(analysis)
    if self.policy == POLICY_GOAL_FIRST_V2_GOAL_LICENSED:
      return self._route_goal_first_v2(analysis, allow_question_with_goal=True)
    return self._route_conservative(analysis)

  def _route_goal_first(self, analysis: StructuredAnalysis) -> RouterDecision:
    """Execute when the task is understood and safe enough to act.

    Ambiguity presence alone does not block execute. Gold Pilot-120 execute
    labels are mostly context-licensed actions, not zero-ambiguity commands.
    Frozen T39 still uses t39_conservative.
    """
    considered: list[str] = ["goal_first_v1"]
    risk = _effective_risk(analysis)
    capability = _effective_capability(analysis)
    targets = _clarification_targets(analysis)
    unresolved = _unresolved_critical(analysis)

    considered.append("known_unsafe_or_prohibited")
    if _is_prohibited(analysis) or (
      risk == RiskLevel.HIGH and "unsafe" in " ".join(analysis.findings).lower()
    ):
      return RouterDecision(
        recommended_strategy=RouteLabel.FACE_PRESERVING_REJECTION,
        strategy_sequence=[],
        matched_rule_id="known_unsafe_or_prohibited",
        considered_rules=considered,
        rejection_reason="unsafe_or_prohibited_action",
      )

    considered.append("known_incapable")
    if capability == CapabilityStatus.INCAPABLE:
      return RouterDecision(
        recommended_strategy=RouteLabel.FACE_PRESERVING_REJECTION,
        strategy_sequence=[],
        matched_rule_id="known_incapable",
        considered_rules=considered,
        rejection_reason="known_incapability",
      )

    considered.append("context_licensed_execute")
    if (
      capability == CapabilityStatus.CAPABLE
      and risk in (RiskLevel.NONE, RiskLevel.LOW)
      and (analysis.speech_act or "") in _ACTIONABLE_SPEECH_ACTS
    ):
      return RouterDecision(
        recommended_strategy=RouteLabel.EXECUTE,
        strategy_sequence=[],
        matched_rule_id="context_licensed_execute",
        considered_rules=considered,
        notes=["goal_first_v1_execute_despite_remaining_ambiguity"],
      )

    considered.append("default_clarify")
    return RouterDecision(
      recommended_strategy=RouteLabel.CLARIFY,
      strategy_sequence=[],
      matched_rule_id="default_clarify",
      considered_rules=considered,
      clarification_targets=targets or unresolved or ["intent"],
      notes=["goal_first_v1_insufficient_licence_to_execute"],
    )

  def _speech_act_allows_execute(
    self, analysis: StructuredAnalysis, *, allow_question_with_goal: bool
  ) -> bool:
    if (analysis.speech_act or "") in _ACTIONABLE_SPEECH_ACTS:
      return True
    if not allow_question_with_goal:
      return False
    summary = (analysis.intent_summary or "").strip()
    if not summary or "?" in summary:
      return False
    return (analysis.speech_act or "") in _QUESTION_SHAPED_ACTS

  def _route_goal_first_v2(
    self, analysis: StructuredAnalysis, *, allow_question_with_goal: bool = False
  ) -> RouterDecision:
    """Act when the job is understood and safe; do not require zero ambiguity.

    Frozen T39 still uses t39_conservative. v1 already executes capable+low-risk
    actionable speech acts. v2 also executes verified-enough conditionals and
    refuses unauthorised/unsafe capability instead of asking again.
    """
    considered: list[str] = ["goal_first_v2"]
    risk = _effective_risk(analysis)
    capability = _effective_capability(analysis)
    targets = _clarification_targets(analysis)
    unresolved = _unresolved_critical(analysis)
    findings = " ".join(analysis.findings).lower()
    pilot = _pilot_capability_label(analysis)

    considered.append("known_unsafe_or_prohibited")
    # Unauthorized alone is not enough to refuse at low/none risk: Pilot-120
    # gold treats many low-risk unauthorized model bits as ask/execute, while
    # true bans still refuse via prohibited findings, unsafe pilot, or elevated
    # risk. Keep refusing unauthorized when risk is medium/high/unknown.
    unauthorized_elevated = pilot == "unauthorized" and risk not in (
      RiskLevel.NONE,
      RiskLevel.LOW,
    )
    if (
      _is_prohibited(analysis)
      or (risk == RiskLevel.HIGH and "unsafe" in findings)
      or pilot == "unsafe"
      or unauthorized_elevated
    ):
      return RouterDecision(
        recommended_strategy=RouteLabel.FACE_PRESERVING_REJECTION,
        strategy_sequence=[],
        matched_rule_id="known_unsafe_or_prohibited",
        considered_rules=considered,
        rejection_reason="unsafe_or_prohibited_action",
      )

    considered.append("known_incapable")
    if capability == CapabilityStatus.INCAPABLE or pilot == "incapable":
      return RouterDecision(
        recommended_strategy=RouteLabel.FACE_PRESERVING_REJECTION,
        strategy_sequence=[],
        matched_rule_id="known_incapable",
        considered_rules=considered,
        rejection_reason="known_incapability",
      )

    considered.append("unknown_capability_high_risk")
    if capability in (None, CapabilityStatus.UNKNOWN) and risk in (
      RiskLevel.MEDIUM,
      RiskLevel.HIGH,
      RiskLevel.UNKNOWN,
    ):
      return RouterDecision(
        recommended_strategy=RouteLabel.FACE_PRESERVING_REJECTION,
        strategy_sequence=[],
        matched_rule_id="unknown_capability_high_risk",
        considered_rules=considered,
        rejection_reason="unknown_capability_unsafe_to_act",
      )

    considered.append("context_licensed_execute")
    capable_enough = capability in (CapabilityStatus.CAPABLE, CapabilityStatus.CONDITIONAL)
    safe_enough = risk in (RiskLevel.NONE, RiskLevel.LOW)
    if capable_enough and safe_enough and self._speech_act_allows_execute(
      analysis, allow_question_with_goal=allow_question_with_goal
    ):
      notes = ["goal_first_v2_execute_despite_remaining_ambiguity"]
      if allow_question_with_goal and (analysis.speech_act or "") not in _ACTIONABLE_SPEECH_ACTS:
        notes.append("goal_licensed_despite_question_shaped_speech_act")
      return RouterDecision(
        recommended_strategy=RouteLabel.EXECUTE,
        strategy_sequence=[],
        matched_rule_id="context_licensed_execute",
        considered_rules=considered,
        notes=notes,
      )

    considered.append("default_clarify")
    return RouterDecision(
      recommended_strategy=RouteLabel.CLARIFY,
      strategy_sequence=[],
      matched_rule_id="default_clarify",
      considered_rules=considered,
      clarification_targets=targets or unresolved or ["intent"],
      notes=["goal_first_v2_insufficient_licence_to_execute"],
    )

  def _route_conservative(self, analysis: StructuredAnalysis) -> RouterDecision:
    considered: list[str] = []
    unresolved = _unresolved_critical(analysis)
    risk = _effective_risk(analysis)
    capability = _effective_capability(analysis)
    targets = _clarification_targets(analysis)
    notes: list[str] = []

    # Rank 1 — known unsafe/prohibited (evidence-based; speech_act alone is insufficient)
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

    # Unknown / missing capability fail-safe (before execute paths)
    considered.append("unknown_or_unverified_capability")
    if capability in (None, CapabilityStatus.UNKNOWN):
      return RouterDecision(
        recommended_strategy=RouteLabel.CLARIFY,
        strategy_sequence=[],
        matched_rule_id="unknown_capability",
        considered_rules=considered,
        clarification_targets=targets or unresolved or ["capability"],
        notes=["unknown_capability_cannot_execute"],
      )
    if capability == CapabilityStatus.CONDITIONAL and not _conditions_verified(analysis):
      return RouterDecision(
        recommended_strategy=RouteLabel.CLARIFY,
        strategy_sequence=[],
        matched_rule_id="unverified_conditional_capability",
        considered_rules=considered,
        clarification_targets=targets or unresolved or ["conditions"],
        notes=["conditional_capability_requires_verified_conditions"],
      )

    # Rank 3 — hazard identity unresolved
    considered.append("hazard_identity_unresolved")
    if _has_hazard_identity_ambiguity(analysis) and unresolved and not _dependent_compound(analysis):
      return RouterDecision(
        recommended_strategy=RouteLabel.CLARIFY,
        strategy_sequence=[],
        matched_rule_id="hazard_identity_unresolved",
        considered_rules=considered,
        clarification_targets=targets or unresolved,
      )

    # Rank 4 — critical unresolved medium/high risk (no execute precommit)
    considered.append("critical_unresolved_medium_high_risk")
    if unresolved and risk in (RiskLevel.MEDIUM, RiskLevel.HIGH):
      if _dependent_compound(analysis):
        return _multi_step_clarify_only(
          matched_rule_id="critical_unresolved_medium_high_risk",
          considered=considered,
          targets=targets or unresolved,
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

    # Unknown / missing risk fail-safe
    considered.append("unknown_safety_risk")
    if risk in (None, RiskLevel.UNKNOWN):
      # Missing risk is never treated as safe for silent resolve or execute.
      if _dependent_compound(analysis):
        return _multi_step_clarify_only(
          matched_rule_id="unknown_safety_risk",
          considered=considered,
          targets=targets or unresolved or ["risk"],
          notes=["unknown_risk_cannot_execute"],
        )
      return RouterDecision(
        recommended_strategy=RouteLabel.CLARIFY,
        strategy_sequence=[],
        matched_rule_id="unknown_safety_risk",
        considered_rules=considered,
        clarification_targets=targets or unresolved or ["risk"],
        notes=["unknown_risk_cannot_execute", "unknown_risk_cannot_silently_resolve"],
      )

    # Rank 5 — dependent compound
    considered.append("dependent_compound_ambiguities")
    if _dependent_compound(analysis):
      return _multi_step_clarify_only(
        matched_rule_id="dependent_compound_ambiguities",
        considered=considered,
        targets=targets or unresolved,
        notes=["later_silent_resolve_only_after_re_evaluation"],
      )

    # Rank 6 — unique low-risk resolvable
    considered.append("unique_low_risk_resolvable")
    if (
      analysis.resolved_slots
      and risk in (RiskLevel.NONE, RiskLevel.LOW)
      and not unresolved
      and (analysis.ambiguity_present or analysis.ambiguity_types)
      and capability in (CapabilityStatus.CAPABLE, CapabilityStatus.CONDITIONAL)
      and (capability != CapabilityStatus.CONDITIONAL or _conditions_verified(analysis))
    ):
      return RouterDecision(
        recommended_strategy=RouteLabel.SILENTLY_RESOLVE,
        strategy_sequence=[],
        matched_rule_id="unique_low_risk_resolvable",
        considered_rules=considered,
        notes=["requires_resolved_slots"],
      )

    # Rank 7 — clear safe capable (explicit positive support only; None is not safe)
    considered.append("clear_safe_capable")
    if (
      not unresolved
      and not analysis.ambiguity_present
      and not analysis.ambiguity_types
      and risk in (RiskLevel.NONE, RiskLevel.LOW)
      and (
        capability == CapabilityStatus.CAPABLE
        or (capability == CapabilityStatus.CONDITIONAL and _conditions_verified(analysis))
      )
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
    if strategy == RouteLabel.SILENTLY_RESOLVE and not analysis.resolved_slots:
      raise SystemsContractError("silently_resolve requires resolved slot values")
    if strategy == RouteLabel.SILENTLY_RESOLVE and _effective_risk(analysis) in (
      None,
      RiskLevel.UNKNOWN,
    ):
      raise SystemsContractError("silently_resolve blocked under unknown risk")
    if strategy == RouteLabel.EXECUTE and _unresolved_critical(analysis):
      raise SystemsContractError("execute blocked with unresolved critical safety slots")
    if strategy == RouteLabel.EXECUTE and _effective_risk(analysis) in (None, RiskLevel.UNKNOWN):
      raise SystemsContractError("execute blocked under unknown risk")
    if strategy == RouteLabel.EXECUTE and _effective_capability(analysis) in (
      None,
      CapabilityStatus.UNKNOWN,
    ):
      raise SystemsContractError("execute blocked under unknown capability")
    if strategy == RouteLabel.EXECUTE and analysis.capability_status == CapabilityStatus.CONDITIONAL:
      if not _conditions_verified(analysis):
        raise SystemsContractError("execute blocked under unverified conditional capability")
    if strategy == RouteLabel.MULTI_STEP:
      if not decision.strategy_sequence:
        raise SystemsContractError("multi_step requires a non-empty strategy_sequence")
      if RouteLabel.EXECUTE in decision.strategy_sequence and _unresolved_critical(analysis):
        raise SystemsContractError(
          "impossible strategy sequence: execute precommit with unresolved critical slots"
        )
      if not decision.requires_re_evaluation and RouteLabel.CLARIFY in decision.strategy_sequence:
        # Allow legacy multi-step only when re-evaluation is explicit for clarify-first plans.
        if any(
          s in (RouteLabel.EXECUTE, RouteLabel.SILENTLY_RESOLVE) for s in decision.strategy_sequence[1:]
        ):
          raise SystemsContractError(
            "multi_step clarify plans require requires_re_evaluation before later actions"
          )
    if strategy == RouteLabel.CLARIFY and not decision.clarification_targets:
      raise SystemsContractError("clarify requires clarification targets")
    if strategy == RouteLabel.FACE_PRESERVING_REJECTION and not decision.rejection_reason:
      raise SystemsContractError("rejection requires a rejection reason")
    if RouteLabel.SILENTLY_RESOLVE in decision.strategy_sequence:
      if analysis.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH) and _unresolved_critical(analysis):
        raise SystemsContractError(
          "impossible strategy sequence: silent resolve under unresolved medium/high risk"
        )


def apply_router_decision(analysis: StructuredAnalysis, decision: RouterDecision) -> StructuredAnalysis:
  from ambiguity_manager.systems.analysis import analysis_from_cached

  working = analysis_from_cached(analysis)
  working.recommended_strategy = decision.recommended_strategy
  working.strategy_sequence = list(decision.strategy_sequence)
  working.clarification_targets = list(decision.clarification_targets)
  working.rejection_reason = decision.rejection_reason
  if decision.requires_re_evaluation:
    working.findings = list(working.findings) + ["requires_re_evaluation"]
  return working
