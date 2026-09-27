from __future__ import annotations

import unittest

from ambiguity_manager.schema.v2.records import CPC, CPCSlot, CandidateInterpretationFrame, ResolvedSlotValue
from ambiguity_manager.schema.v2.taxonomies import CPCSlotStatus
from ambiguity_manager.systems.contracts import StructuredAnalysis
from ambiguity_manager.systems.response_generation import (
    DeterministicClarificationGenerator,
    DeterministicRejectionGenerator,
    generate_clarification,
    generate_rejection,
)


def _cpc(**filled: str) -> CPC:
    c = CPC.empty_unknown()
    for key, value in filled.items():
        setattr(c, key, CPCSlot(value=value, status=CPCSlotStatus.FILLED))
    return c


class T22ResponseGenerationTests(unittest.TestCase):
    def test_clarification_addresses_target(self) -> None:
        analysis = StructuredAnalysis(
            intent_summary="bring mug",
            candidate_interpretations=[
                CandidateInterpretationFrame(frame_id="f1", text="bring red mug", cpc=_cpc(object="red mug")),
                CandidateInterpretationFrame(frame_id="f2", text="bring blue mug", cpc=_cpc(object="blue mug")),
            ],
        )

        text = generate_clarification(analysis, ["object"])

        self.assertIn("red mug", text)
        self.assertIn("blue mug", text)
        self.assertNotIn("left or right", text)

    def test_clarification_deduplicates_targets_and_skips_resolved_ones(self) -> None:
        analysis = StructuredAnalysis(
            resolved_slots=[ResolvedSlotValue(slot_name="object", value="red mug")],
        )
        generator = DeterministicClarificationGenerator()

        text = generator.generate_clarification(analysis, ["object", "object", "destination", "destination"])

        self.assertEqual(text, "Could you clarify the destination?")
        self.assertNotIn("left or right", text)
    def test_face_preserving_rejection_is_used(self) -> None:
        analysis = StructuredAnalysis()

        text = generate_rejection(analysis, "unsafe_or_prohibited_action")

        self.assertIn("I need to decline", text)
        self.assertIn("unsafe", text)

    def test_rejection_does_not_invent_alternative(self) -> None:
        analysis = StructuredAnalysis(resolved_slots=[])

        text = generate_rejection(analysis, "known_incapability")

        self.assertNotRegex(text, r"(?<!un)supported alternative")
        self.assertIn("I will not invent an alternative that is not supported.", text)

    def test_wording_is_deterministic(self) -> None:
        analysis = StructuredAnalysis(
            candidate_interpretations=[CandidateInterpretationFrame(frame_id="f1", text="chemical container", cpc=_cpc(object="chemical container"))],
            intent_summary="move chemical container",
        )

        clarification_a = generate_clarification(analysis, ["safety_precondition"])
        clarification_b = generate_clarification(analysis, ["safety_precondition"])
        rejection_a = DeterministicRejectionGenerator().generate_rejection(analysis, "capability_limitation")
        rejection_b = DeterministicRejectionGenerator().generate_rejection(analysis, "capability_limitation")

        self.assertEqual(clarification_a, clarification_b)
        self.assertEqual(rejection_a, rejection_b)

    def test_intent_summary_or_is_used_when_candidates_empty(self) -> None:
        analysis = StructuredAnalysis(
            intent_summary=(
                "Add either 20 millilitres or 60 millilitres of liquid soap "
                "to the dispenser using the dosing cup."
            ),
        )
        text = generate_clarification(analysis, ["quantity", "tool", "recipient"])
        self.assertIn("20 millilitres", text)
        self.assertIn("60 millilitres", text)
        self.assertNotIn("could you clarify:", text.casefold())

    def test_parenthetical_or_in_intent_summary(self) -> None:
        analysis = StructuredAnalysis(
            intent_summary="Deliver one of the two pending serving trays (grey or amber)."
        )
        text = generate_clarification(analysis, ["spatial_relation"])
        self.assertEqual(text, "Do you mean grey or amber?")


if __name__ == "__main__":
    unittest.main()
