from __future__ import annotations

import unittest

from ambiguity_manager.schema.v2.records import (
    CPC,
    CPCSlot,
    CandidateInterpretationFrame,
    EvidenceRef,
    SelectedInterpretation,
    UnresolvedSlot,
)
from ambiguity_manager.schema.v2.taxonomies import CPCSlotStatus, CapabilityStatus, RiskLevel, RouteLabel
from ambiguity_manager.systems.contracts import StructuredAnalysis
from ambiguity_manager.systems.routing import RouterDecision
from ambiguity_manager.systems.safety import SafetyEnforcer


def _cpc(**filled: str) -> CPC:
    c = CPC.empty_unknown()
    for key, value in filled.items():
        setattr(c, key, CPCSlot(value=value, status=CPCSlotStatus.FILLED))
    return c


def _analysis() -> StructuredAnalysis:
    return StructuredAnalysis(
        cpc=_cpc(action="move", object="mug"),
        candidate_interpretations=[
            CandidateInterpretationFrame(frame_id="f1", text="move mug", cpc=_cpc(action="move", object="mug"))
        ],
    )


class T21SafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.enforcer = SafetyEnforcer(policy={"enforcement_mode": "fail_closed"})

    def test_unsupported_commitment_finding(self) -> None:
        analysis = _analysis()
        analysis.selected_interpretation = SelectedInterpretation(frame_id="f1", supporting_evidence=[])

        findings = self.enforcer.check_analysis(analysis)

        self.assertEqual(findings[0].finding_type, "unsupported_commitment")

    def test_unsafe_silent_resolution_finding(self) -> None:
        analysis = _analysis()
        analysis.recommended_strategy = RouteLabel.SILENTLY_RESOLVE
        analysis.risk_level = RiskLevel.HIGH
        analysis.unresolved_slots = [UnresolvedSlot(slot_name="object", reason="referential")]

        findings = self.enforcer.check_route(analysis)
        finding_types = {finding.finding_type for finding in findings}

        self.assertIn("unsafe_silent_resolution", finding_types)

    def test_capability_overcommitment_finding(self) -> None:
        analysis = _analysis()
        analysis.recommended_strategy = RouteLabel.EXECUTE
        analysis.capability_status = CapabilityStatus.INCAPABLE

        findings = self.enforcer.check_route(analysis)

        self.assertTrue(any(f.finding_type == "capability_overcommitment" for f in findings))

    def test_invalid_clarification_finding(self) -> None:
        analysis = _analysis()
        analysis.recommended_strategy = RouteLabel.CLARIFY

        findings = self.enforcer.check_route(analysis)

        self.assertTrue(any(f.finding_type == "invalid_clarification" for f in findings))

    def test_invalid_rejection_finding(self) -> None:
        analysis = _analysis()
        analysis.recommended_strategy = RouteLabel.FACE_PRESERVING_REJECTION

        findings = self.enforcer.check_route(analysis)

        self.assertTrue(any(f.finding_type == "invalid_rejection" for f in findings))

    def test_invalid_strategy_sequence_finding(self) -> None:
        analysis = _analysis()
        analysis.risk_level = RiskLevel.HIGH
        decision = RouterDecision(
            recommended_strategy=RouteLabel.MULTI_STEP,
            strategy_sequence=[RouteLabel.SILENTLY_RESOLVE],
            matched_rule_id="bad_sequence",
            considered_rules=["bad_sequence"],
        )

        findings = self.enforcer.check_route(analysis, decision)
        finding_types = {finding.finding_type for finding in findings}

        self.assertIn("strategy_sequence_violation", finding_types)

    def test_extra_specificity_finding(self) -> None:
        analysis = _analysis()
        analysis.resolved_slots = []
        findings = self.enforcer.check_response_specificity(
            "Please use Atlantis Crate next.",
            analysis,
            "Move the mug.",
        )

        self.assertTrue(any(f.finding_type == "extra_specificity" for f in findings))

    def test_enforce_rejects_fail_closed_critical_route_issue(self) -> None:
        analysis = _analysis()
        analysis.recommended_strategy = RouteLabel.EXECUTE
        analysis.unresolved_slots = [UnresolvedSlot(slot_name="object", reason="referential")]
        enforcement = self.enforcer.enforce(analysis, command="Move it.")

        self.assertTrue(enforcement.reject)
        self.assertEqual(enforcement.action, "reject_result")


if __name__ == "__main__":
    unittest.main()
