"""RED/GREEN regression tests for T19 router hardening.

Covers three related hardening themes that the deterministic router must
respect:

* unknown risk/capability (including untyped ``None`` when the analysis is
  otherwise flagged as safety- or capability-relevant) must never silently
  execute or silently resolve;
* a bare ``speech_act == "prohibition"`` must not, by itself, force a
  rejection -- only genuinely unsafe/prohibited findings should;
* a risky, unresolved compound ambiguity must never pre-bake an ``execute``
  step into the same decision; clarification and execution must be separate,
  re-evaluated decisions.
"""

from __future__ import annotations

import unittest

from ambiguity_manager.schema.v2.records import ResolvedSlotValue, UnresolvedSlot
from ambiguity_manager.schema.v2.taxonomies import AmbiguityType, CapabilityStatus, RiskLevel, RouteLabel
from ambiguity_manager.systems.contracts import StructuredAnalysis
from ambiguity_manager.systems.routing import DeterministicRouter


def _analysis(
    *,
    ambiguity_types: list[AmbiguityType] | None = None,
    ambiguity_present: bool = False,
    unresolved: list[str] | None = None,
    resolved: list[tuple[str, str]] | None = None,
    risk: RiskLevel | None = None,
    risk_relevant: bool = False,
    capability: CapabilityStatus | None = None,
    findings: list[str] | None = None,
    speech_act: str = "directive_command",
) -> StructuredAnalysis:
    return StructuredAnalysis(
        speech_act=speech_act,
        ambiguity_present=ambiguity_present,
        ambiguity_types=list(ambiguity_types or []),
        unresolved_slots=[UnresolvedSlot(slot_name=slot, reason="test") for slot in (unresolved or [])],
        resolved_slots=[
            ResolvedSlotValue(slot_name=slot_name, value=value) for slot_name, value in (resolved or [])
        ],
        risk_level=risk,
        risk_relevant=risk_relevant,
        capability_status=capability,
        findings=list(findings or []),
    )


class T19RouterUnknownsAndProhibitionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = DeterministicRouter(precedence={"version": "test"})

    # -- unknown risk -----------------------------------------------------

    def test_none_risk_treated_as_unknown_when_safety_relevant_cannot_execute(self) -> None:
        analysis = _analysis(risk=None, risk_relevant=True, capability=CapabilityStatus.CAPABLE)

        decision = self.router.route(analysis)

        self.assertNotEqual(
            decision.recommended_strategy,
            RouteLabel.EXECUTE,
            msg="an untyped None risk flagged as safety-relevant must be treated as unknown, not safe",
        )

    def test_none_risk_treated_as_unknown_when_safety_relevant_cannot_silently_resolve(self) -> None:
        analysis = _analysis(
            ambiguity_types=[AmbiguityType.SPATIAL],
            ambiguity_present=True,
            resolved=[("destination", "left table")],
            risk=None,
            risk_relevant=True,
            capability=CapabilityStatus.CAPABLE,
        )

        decision = self.router.route(analysis)

        self.assertNotEqual(decision.recommended_strategy, RouteLabel.SILENTLY_RESOLVE)

    def test_literal_unknown_risk_cannot_execute(self) -> None:
        analysis = _analysis(risk=RiskLevel.UNKNOWN, risk_relevant=True, capability=CapabilityStatus.CAPABLE)

        decision = self.router.route(analysis)

        self.assertNotEqual(decision.recommended_strategy, RouteLabel.EXECUTE)

    def test_literal_unknown_risk_cannot_silently_resolve(self) -> None:
        analysis = _analysis(
            ambiguity_types=[AmbiguityType.SPATIAL],
            ambiguity_present=True,
            resolved=[("destination", "left table")],
            risk=RiskLevel.UNKNOWN,
            capability=CapabilityStatus.CAPABLE,
        )

        decision = self.router.route(analysis)

        self.assertNotEqual(decision.recommended_strategy, RouteLabel.SILENTLY_RESOLVE)

    # -- unknown / conditional capability ----------------------------------

    def test_unknown_capability_cannot_execute(self) -> None:
        analysis = _analysis(risk=RiskLevel.NONE, capability=CapabilityStatus.UNKNOWN)

        decision = self.router.route(analysis)

        self.assertNotEqual(decision.recommended_strategy, RouteLabel.EXECUTE)

    def test_none_capability_with_capability_uncertain_finding_cannot_execute(self) -> None:
        analysis = _analysis(
            risk=RiskLevel.NONE,
            capability=None,
            findings=["capability_uncertain"],
        )

        decision = self.router.route(analysis)

        self.assertNotEqual(
            decision.recommended_strategy,
            RouteLabel.EXECUTE,
            msg="an untyped None capability must not execute once findings flag capability as uncertain",
        )

    def test_conditional_capability_without_verified_conditions_cannot_execute(self) -> None:
        analysis = _analysis(risk=RiskLevel.NONE, capability=CapabilityStatus.CONDITIONAL, findings=[])

        decision = self.router.route(analysis)

        self.assertNotEqual(decision.recommended_strategy, RouteLabel.EXECUTE)
        self.assertIn(
            decision.recommended_strategy,
            {RouteLabel.CLARIFY, RouteLabel.FACE_PRESERVING_REJECTION},
        )

    def test_conditional_capability_with_verified_conditions_can_execute(self) -> None:
        analysis = _analysis(
            risk=RiskLevel.NONE,
            capability=CapabilityStatus.CONDITIONAL,
            findings=["conditions_verified"],
        )

        decision = self.router.route(analysis)

        self.assertEqual(decision.recommended_strategy, RouteLabel.EXECUTE)

    def test_clear_case_with_explicit_none_risk_and_capable_still_executes(self) -> None:
        analysis = _analysis(risk=RiskLevel.NONE, capability=CapabilityStatus.CAPABLE)

        decision = self.router.route(analysis)

        self.assertEqual(decision.recommended_strategy, RouteLabel.EXECUTE)
        self.assertEqual(decision.matched_rule_id, "clear_safe_capable")

    # -- prohibitions -------------------------------------------------------

    def test_safe_prohibition_without_unsafe_findings_is_not_rejected(self) -> None:
        analysis = _analysis(
            risk=RiskLevel.LOW,
            capability=CapabilityStatus.CAPABLE,
            findings=[],
            speech_act="prohibition",
        )

        decision = self.router.route(analysis)

        self.assertNotEqual(
            decision.recommended_strategy,
            RouteLabel.FACE_PRESERVING_REJECTION,
            msg="speech_act='prohibition' alone must not force a rejection absent unsafe findings",
        )
        self.assertIn(decision.recommended_strategy, {RouteLabel.EXECUTE, RouteLabel.CLARIFY})

    def test_unsafe_command_with_unsafe_finding_is_rejected(self) -> None:
        analysis = _analysis(
            risk=RiskLevel.HIGH,
            capability=CapabilityStatus.CAPABLE,
            findings=["unsafe_action"],
            speech_act="directive_command",
        )

        decision = self.router.route(analysis)

        self.assertEqual(decision.recommended_strategy, RouteLabel.FACE_PRESERVING_REJECTION)
        self.assertEqual(decision.rejection_reason, "unsafe_or_prohibited_action")

    def test_ambiguous_prohibition_may_clarify_instead_of_reject(self) -> None:
        analysis = _analysis(
            ambiguity_types=[AmbiguityType.REFERENTIAL],
            ambiguity_present=True,
            unresolved=["object"],
            risk=RiskLevel.LOW,
            capability=CapabilityStatus.CAPABLE,
            findings=[],
            speech_act="prohibition",
        )

        decision = self.router.route(analysis)

        self.assertNotEqual(decision.recommended_strategy, RouteLabel.FACE_PRESERVING_REJECTION)
        self.assertIn(decision.recommended_strategy, {RouteLabel.CLARIFY, RouteLabel.MULTI_STEP})

    # -- risky unresolved compounds -----------------------------------------

    def test_risky_unresolved_compound_cannot_prebake_execute(self) -> None:
        analysis = _analysis(
            ambiguity_types=[AmbiguityType.REFERENTIAL, AmbiguityType.SAFETY_PRECONDITION],
            ambiguity_present=True,
            unresolved=["object", "destination"],
            risk=RiskLevel.HIGH,
            capability=CapabilityStatus.CAPABLE,
        )

        decision = self.router.route(analysis)

        self.assertNotIn(
            RouteLabel.EXECUTE,
            decision.strategy_sequence,
            msg="a risky unresolved compound must never pre-bake execute into the strategy sequence",
        )
        self.assertIn(decision.recommended_strategy, {RouteLabel.CLARIFY, RouteLabel.MULTI_STEP})
        self.assertTrue(
            any("re_evaluat" in note for note in decision.notes),
            msg="the decision must flag that a re-evaluation is required after clarification",
        )

    def test_after_simulated_clarification_execute_selected_in_separate_decision(self) -> None:
        initial = _analysis(
            ambiguity_types=[AmbiguityType.REFERENTIAL, AmbiguityType.SAFETY_PRECONDITION],
            ambiguity_present=True,
            unresolved=["object", "destination"],
            risk=RiskLevel.HIGH,
            capability=CapabilityStatus.CAPABLE,
        )
        first_decision = self.router.route(initial)
        self.assertNotIn(RouteLabel.EXECUTE, first_decision.strategy_sequence)

        clarified = _analysis(
            resolved=[("object", "mug"), ("destination", "table")],
            risk=RiskLevel.LOW,
            capability=CapabilityStatus.CAPABLE,
        )
        second_decision = self.router.route(clarified)

        self.assertEqual(second_decision.recommended_strategy, RouteLabel.EXECUTE)
        self.assertNotEqual(
            first_decision.matched_rule_id,
            second_decision.matched_rule_id,
            msg="execute must come from a distinct, later routing decision, not the original one",
        )


if __name__ == "__main__":
    unittest.main()
