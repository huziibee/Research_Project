from __future__ import annotations

from ambiguity_manager.schema.v2.taxonomies import AmbiguityType, CapabilityStatus, RiskLevel, RouteLabel
from ambiguity_manager.systems.contracts import StructuredAnalysis
from ambiguity_manager.systems.routing import DeterministicRouter, POLICY_GOAL_FIRST_V1, POLICY_T39_CONSERVATIVE


def _analysis() -> StructuredAnalysis:
    return StructuredAnalysis(
        speech_act="directive_command",
        ambiguity_present=True,
        ambiguity_types=[AmbiguityType.TEMPORAL],
        capability_status=CapabilityStatus.CAPABLE,
        risk_level=RiskLevel.LOW,
    )


def test_conservative_policy_will_not_execute_when_ambiguity_remains():
    decision = DeterministicRouter(policy=POLICY_T39_CONSERVATIVE).route(_analysis())
    assert decision.recommended_strategy == RouteLabel.CLARIFY


def test_goal_first_executes_capable_low_risk_despite_ambiguity():
    decision = DeterministicRouter(policy=POLICY_GOAL_FIRST_V1).route(_analysis())
    assert decision.recommended_strategy == RouteLabel.EXECUTE
    assert decision.matched_rule_id == "context_licensed_execute"


def test_goal_first_still_rejects_incapable():
    analysis = _analysis()
    analysis.capability_status = CapabilityStatus.INCAPABLE
    decision = DeterministicRouter(policy=POLICY_GOAL_FIRST_V1).route(analysis)
    assert decision.recommended_strategy == RouteLabel.FACE_PRESERVING_REJECTION


def test_default_router_stays_conservative():
    assert DeterministicRouter().policy == POLICY_T39_CONSERVATIVE
