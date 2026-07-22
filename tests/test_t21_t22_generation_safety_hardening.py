"""RED/GREEN regression tests for T21/T22 generation-safety hardening.

Locks in the intended contract for clarification generation and the
response-specificity safety check:

* clarification text may only offer options that candidates actually
  support -- hard-coded "left or right table" wording must not appear when
  no candidate mentions a left/right split;
* when candidates are unknown, clarification must ask an open, slot-specific
  question instead of inventing spatial options;
* multi-target clarification stays concise and grounded in the requested
  slots;
* generic politeness/template openers (e.g. "Could you clarify...",
  "Sorry, before I continue...") must never be flagged as extra specificity;
* genuinely invented named entities (e.g. "Atlantis") must still be flagged;
* previously-recorded unsupported alternatives must remain visible findings.
"""

from __future__ import annotations

import unittest

from ambiguity_manager.schema.v2.records import CPC, CPCSlot, CandidateInterpretationFrame
from ambiguity_manager.schema.v2.taxonomies import CPCSlotStatus
from ambiguity_manager.systems.contracts import StructuredAnalysis
from ambiguity_manager.systems.response_generation import generate_clarification
from ambiguity_manager.systems.safety import SafetyEnforcer


def _cpc(**filled: str) -> CPC:
    c = CPC.empty_unknown()
    for key, value in filled.items():
        setattr(c, key, CPCSlot(value=value, status=CPCSlotStatus.FILLED))
    return c


class T21T22GenerationSafetyHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.enforcer = SafetyEnforcer(policy={"enforcement_mode": "fail_closed"})

    # -- clarification generation -------------------------------------------

    def test_destination_clarification_does_not_invent_left_right_when_unsupported(self) -> None:
        analysis = StructuredAnalysis(
            intent_summary="put cup on table",
            candidate_interpretations=[
                CandidateInterpretationFrame(
                    frame_id="f1", text="put cup on table", cpc=_cpc(destination="table")
                ),
            ],
        )

        text = generate_clarification(analysis, ["destination"])

        self.assertNotIn("left", text.lower())
        self.assertNotIn("right", text.lower())

    def test_candidate_derived_clarification_options_are_allowed(self) -> None:
        analysis = StructuredAnalysis(
            candidate_interpretations=[
                CandidateInterpretationFrame(
                    frame_id="f1", text="put cup on left table", cpc=_cpc(destination="left table")
                ),
                CandidateInterpretationFrame(
                    frame_id="f2", text="put cup on right table", cpc=_cpc(destination="right table")
                ),
            ],
        )

        text = generate_clarification(analysis, ["destination"])

        self.assertIn("left", text.lower())
        self.assertIn("right", text.lower())

    def test_open_slot_specific_question_when_candidates_unknown(self) -> None:
        analysis = StructuredAnalysis(candidate_interpretations=[])

        text = generate_clarification(analysis, ["destination"])

        self.assertNotIn(
            "left",
            text.lower(),
            msg="with no candidates to ground it, clarification must ask an open question, not invent options",
        )
        self.assertNotIn("right", text.lower())
        self.assertTrue(text.strip().endswith("?"))

    def test_multitarget_clarification_is_concise_and_grounded(self) -> None:
        analysis = StructuredAnalysis(resolved_slots=[])

        text = generate_clarification(analysis, ["object", "destination"])

        self.assertLessEqual(len(text.split()), 20)
        self.assertIn("object", text.lower())
        self.assertIn("destination", text.lower())
        self.assertNotIn("left", text.lower())
        self.assertNotIn("right", text.lower())

    # -- response specificity safety check ----------------------------------

    def test_could_you_clarify_is_not_flagged_as_extra_specificity(self) -> None:
        analysis = StructuredAnalysis()

        findings = self.enforcer.check_response_specificity(
            "Could you clarify what you would like me to do?",
            analysis,
            "Do it.",
        )

        self.assertEqual(
            findings,
            [],
            msg="a generic 'Could you clarify...' opener must not be flagged as extra specificity",
        )

    def test_invented_named_object_is_flagged(self) -> None:
        analysis = StructuredAnalysis()

        findings = self.enforcer.check_response_specificity(
            "Please use the Atlantis crate next.",
            analysis,
            "Move the mug.",
        )

        self.assertTrue(
            any("Atlantis" in f.message for f in findings),
            msg="a genuinely invented named object must still be flagged",
        )

    def test_template_politeness_is_ignored(self) -> None:
        analysis = StructuredAnalysis()

        findings = self.enforcer.check_response_specificity(
            "Sorry, before I continue, should I proceed?",
            analysis,
            "Proceed.",
        )

        self.assertEqual(findings, [])

    def test_unsupported_alternatives_remain_as_findings(self) -> None:
        analysis = StructuredAnalysis(
            unsupported_specificity=["unsupported_specificity:object=golden cup"],
        )

        findings = self.enforcer.check_analysis(analysis)

        self.assertTrue(any(f.finding_type == "extra_specificity" for f in findings))
        self.assertIn("golden cup", findings[0].message)


if __name__ == "__main__":
    unittest.main()
