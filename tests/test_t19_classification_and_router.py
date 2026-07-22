from __future__ import annotations

import unittest

from ambiguity_manager.schema.v2.records import CPC, CPCSlot, ResolvedSlotValue, UnresolvedSlot
from ambiguity_manager.schema.v2.taxonomies import (
    AmbiguityType,
    CPCSlotStatus,
    CapabilityStatus,
    RiskLevel,
    RouteLabel,
)
from ambiguity_manager.systems.classification import apply_classification_aggregate, derive_ambiguity_fields
from ambiguity_manager.systems.contracts import StructuredAnalysis
from ambiguity_manager.systems.errors import SystemsContractError
from ambiguity_manager.systems.routing import DeterministicRouter, RouterDecision, apply_router_decision


def _cpc(**filled: str) -> CPC:
    c = CPC.empty_unknown()
    for key, value in filled.items():
        setattr(c, key, CPCSlot(value=value, status=CPCSlotStatus.FILLED))
    return c


def _analysis(
    *,
    ambiguity_types: list[AmbiguityType] | None = None,
    ambiguity_present: bool = False,
    unresolved: list[str] | None = None,
    resolved: list[tuple[str, str]] | None = None,
    risk: RiskLevel | None = None,
    capability: CapabilityStatus | None = None,
    findings: list[str] | None = None,
    speech_act: str = "directive_command",
) -> StructuredAnalysis:
    return StructuredAnalysis(
        speech_act=speech_act,
        cpc=_cpc(action="move", object="mug"),
        ambiguity_present=ambiguity_present,
        ambiguity_types=list(ambiguity_types or []),
        unresolved_slots=[UnresolvedSlot(slot_name=slot, reason="test") for slot in (unresolved or [])],
        resolved_slots=[
            ResolvedSlotValue(slot_name=slot_name, value=value)
            for slot_name, value in (resolved or [])
        ],
        risk_level=risk,
        capability_status=capability,
        findings=list(findings or []),
    )


class T19ClassificationAndRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = DeterministicRouter(precedence={"version": "test"})

    def test_classification_aggregation_applies_compound_fields(self) -> None:
        analysis = _analysis(
            ambiguity_types=[AmbiguityType.REFERENTIAL, AmbiguityType.SAFETY_PRECONDITION],
            ambiguity_present=False,
            risk=RiskLevel.HIGH,
            capability=CapabilityStatus.CAPABLE,
        )

        aggregate = derive_ambiguity_fields(analysis)
        applied = apply_classification_aggregate(analysis, aggregate)

        self.assertTrue(aggregate.ambiguity_present)
        self.assertTrue(aggregate.compound_ambiguity)
        self.assertEqual(aggregate.compound_ambiguity_count, 2)
        self.assertIn("ambiguity_present_from_types", aggregate.derivation_notes)
        self.assertEqual(applied.primary_ambiguity_type, AmbiguityType.REFERENTIAL)
        self.assertTrue(applied.risk_relevant)

    def test_router_executes_clear_safe_capable_case(self) -> None:
        analysis = _analysis(risk=RiskLevel.NONE, capability=CapabilityStatus.CAPABLE)

        decision = self.router.route(analysis)

        self.assertEqual(decision.recommended_strategy, RouteLabel.EXECUTE)
        self.assertEqual(decision.matched_rule_id, "clear_safe_capable")

    def test_router_silently_resolves_unique_low_risk_case(self) -> None:
        analysis = _analysis(
            ambiguity_types=[AmbiguityType.SPATIAL],
            ambiguity_present=True,
            resolved=[("destination", "left table")],
            risk=RiskLevel.LOW,
            capability=CapabilityStatus.CAPABLE,
        )

        decision = self.router.route(analysis)

        self.assertEqual(decision.recommended_strategy, RouteLabel.SILENTLY_RESOLVE)
        self.assertEqual(decision.matched_rule_id, "unique_low_risk_resolvable")
        self.assertIn("requires_resolved_slots", decision.notes)

    def test_medium_high_risk_never_silent(self) -> None:
        analysis = _analysis(
            ambiguity_types=[AmbiguityType.REFERENTIAL],
            ambiguity_present=True,
            unresolved=["object"],
            risk=RiskLevel.MEDIUM,
            capability=CapabilityStatus.CAPABLE,
        )

        decision = self.router.route(analysis)

        self.assertEqual(decision.recommended_strategy, RouteLabel.CLARIFY)
        self.assertNotEqual(decision.recommended_strategy, RouteLabel.SILENTLY_RESOLVE)
        self.assertIn("never_silently_resolve_medium_high_risk", decision.notes)

    def test_unknown_risk_clarifies(self) -> None:
        analysis = _analysis(
            ambiguity_types=[AmbiguityType.SAFETY_PRECONDITION],
            ambiguity_present=True,
            unresolved=["conditions"],
            risk=RiskLevel.UNKNOWN,
            capability=CapabilityStatus.CONDITIONAL,
        )
        analysis.risk_relevant = True

        decision = self.router.route(analysis)

        self.assertEqual(decision.recommended_strategy, RouteLabel.CLARIFY)
        self.assertEqual(decision.matched_rule_id, "unknown_safety_risk")
        self.assertEqual(decision.clarification_targets, ["conditions"])

    def test_known_incapable_rejects(self) -> None:
        analysis = _analysis(risk=RiskLevel.NONE, capability=CapabilityStatus.INCAPABLE)

        decision = self.router.route(analysis)

        self.assertEqual(decision.recommended_strategy, RouteLabel.FACE_PRESERVING_REJECTION)
        self.assertEqual(decision.rejection_reason, "known_incapability")

    def test_prohibited_action_rejects(self) -> None:
        analysis = _analysis(
            risk=RiskLevel.HIGH,
            capability=CapabilityStatus.CAPABLE,
            findings=["unsafe_action", "prohibited"],
            speech_act="prohibition",
        )

        decision = self.router.route(analysis)

        self.assertEqual(decision.recommended_strategy, RouteLabel.FACE_PRESERVING_REJECTION)
        self.assertEqual(decision.rejection_reason, "unsafe_or_prohibited_action")

    def test_dependent_compound_high_risk_returns_multi_step(self) -> None:
        analysis = _analysis(
            ambiguity_types=[AmbiguityType.REFERENTIAL, AmbiguityType.SAFETY_PRECONDITION],
            ambiguity_present=True,
            unresolved=["object", "destination"],
            risk=RiskLevel.HIGH,
            capability=CapabilityStatus.CAPABLE,
        )

        decision = self.router.route(analysis)

        self.assertEqual(decision.recommended_strategy, RouteLabel.MULTI_STEP)
        self.assertEqual(decision.strategy_sequence, [RouteLabel.CLARIFY, RouteLabel.EXECUTE])
        self.assertEqual(decision.matched_rule_id, "critical_unresolved_medium_high_risk")

    def test_router_validation_requires_resolved_slots_for_silent(self) -> None:
        analysis = _analysis(
            ambiguity_types=[AmbiguityType.SPATIAL],
            ambiguity_present=True,
            resolved=[],
            risk=RiskLevel.LOW,
        )
        decision = RouterDecision(
            recommended_strategy=RouteLabel.SILENTLY_RESOLVE,
            strategy_sequence=[],
            matched_rule_id="test_silent",
            considered_rules=["test_silent"],
        )

        with self.assertRaises(SystemsContractError):
            self.router.validate_decision(decision, analysis)

    def test_router_validation_blocks_execute_with_unresolved_critical_slots(self) -> None:
        analysis = _analysis(unresolved=["object"], risk=RiskLevel.NONE, capability=CapabilityStatus.CAPABLE)
        decision = self.router.route(_analysis(risk=RiskLevel.NONE, capability=CapabilityStatus.CAPABLE))
        decision = apply_router_decision(analysis, decision)

        with self.assertRaises(SystemsContractError):
            self.router.validate_decision(decision, analysis)

    def test_router_trace_is_deterministic(self) -> None:
        analysis = _analysis(
            ambiguity_types=[AmbiguityType.REFERENTIAL],
            ambiguity_present=True,
            unresolved=["object"],
            risk=RiskLevel.LOW,
        )

        first = self.router.route(analysis).to_dict()
        second = self.router.route(analysis).to_dict()

        self.assertEqual(first, second)
        self.assertEqual(first["matched_rule_id"], "default_clarify")


if __name__ == "__main__":
    unittest.main()
