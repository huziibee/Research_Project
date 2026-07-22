from __future__ import annotations

import unittest

from ambiguity_manager.schema.v2.records import CPC, CPCSlot, CandidateInterpretationFrame, SelectedInterpretation
from ambiguity_manager.schema.v2.taxonomies import CPCSlotStatus, RouteLabel
from ambiguity_manager.systems.uncertainty import (
    categorical_entropy,
    compute_uncertainty_diagnostics,
    scalar_uncertainty_score,
    variation_ratio,
)
from ambiguity_manager.systems.contracts import StructuredAnalysis


def _cpc(**filled: str) -> CPC:
    c = CPC.empty_unknown()
    for key, value in filled.items():
        setattr(c, key, CPCSlot(value=value, status=CPCSlotStatus.FILLED))
    return c


def _analysis(
    *,
    intent: str = "directive_command",
    action: str = "pick",
    obj: str = "red mug",
    frame_id: str = "f1",
    route: RouteLabel = RouteLabel.EXECUTE,
) -> StructuredAnalysis:
    candidate = CandidateInterpretationFrame(
        frame_id=frame_id,
        text=f"{action} {obj}",
        cpc=_cpc(action=action, object=obj),
    )
    return StructuredAnalysis(
        speech_act=intent,
        cpc=_cpc(action=action, object=obj),
        candidate_interpretations=[candidate],
        selected_interpretation=SelectedInterpretation(frame_id=frame_id, supporting_evidence=[]),
        recommended_strategy=route,
    )


class T18UncertaintyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = {
            "minimum_sample_count": 2,
            "status": "development_only",
            "valid_for_official_use": False,
            "frozen": False,
        }

    def test_zero_disagreement(self) -> None:
        samples = [_analysis(), _analysis()]

        diagnostics = compute_uncertainty_diagnostics(samples, policy=self.policy)

        self.assertEqual(diagnostics.total_sample_count, 2)
        self.assertFalse(diagnostics.insufficient_samples)
        self.assertEqual(diagnostics.candidate_set_disagreement, 0.0)
        self.assertEqual(diagnostics.selected_interpretation_disagreement, 0.0)
        self.assertEqual(diagnostics.intent_disagreement, 0.0)
        self.assertEqual(diagnostics.cpc_slot_disagreement["action"], 0.0)
        self.assertEqual(scalar_uncertainty_score(diagnostics), 0.0)

    def test_intent_disagreement_metrics(self) -> None:
        samples = [
            _analysis(intent="directive_command"),
            _analysis(intent="indirect_request"),
        ]

        diagnostics = compute_uncertainty_diagnostics(samples, policy=self.policy)

        self.assertEqual(diagnostics.intent_disagreement, 1.0)
        self.assertEqual(categorical_entropy(["directive_command", "indirect_request"]), 1.0)
        self.assertEqual(variation_ratio(["directive_command", "indirect_request"]), 0.5)

    def test_cpc_disagreement_detected(self) -> None:
        samples = [
            _analysis(action="pick", obj="red mug"),
            _analysis(action="pick", obj="blue mug"),
        ]

        diagnostics = compute_uncertainty_diagnostics(samples, policy=self.policy)

        self.assertEqual(diagnostics.cpc_slot_disagreement["action"], 0.0)
        self.assertEqual(diagnostics.cpc_slot_disagreement["object"], 1.0)
        self.assertEqual(diagnostics.per_slot_support_counts["object"]["red mug"], 1)
        self.assertEqual(diagnostics.per_slot_support_counts["object"]["blue mug"], 1)

    def test_candidate_set_disagreement_detected(self) -> None:
        samples = [
            _analysis(frame_id="f1", obj="red mug"),
            _analysis(frame_id="f2", obj="blue mug"),
        ]

        diagnostics = compute_uncertainty_diagnostics(samples, policy=self.policy)

        self.assertEqual(diagnostics.candidate_set_disagreement, 1.0)
        self.assertEqual(diagnostics.selected_interpretation_disagreement, 1.0)

    def test_insufficient_samples_flagged(self) -> None:
        diagnostics = compute_uncertainty_diagnostics([_analysis()], policy=self.policy)

        self.assertTrue(diagnostics.insufficient_samples)
        self.assertEqual(diagnostics.total_sample_count, 1)

    def test_output_is_deterministic_for_same_samples(self) -> None:
        samples = [
            _analysis(intent="directive_command", action="pick", obj="red mug"),
            _analysis(intent="directive_command", action="pick", obj="red mug"),
        ]

        first = compute_uncertainty_diagnostics(samples, policy=self.policy)
        second = compute_uncertainty_diagnostics(samples, policy=self.policy)

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.diagnostics_hash, second.diagnostics_hash)


if __name__ == "__main__":
    unittest.main()
