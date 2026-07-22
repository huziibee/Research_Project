from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.schema.v2.records import (
    CPC,
    CPCSlot,
    CandidateInterpretationFrame,
    EvidenceRef,
    SelectedInterpretation,
    UnresolvedSlot,
)
from ambiguity_manager.schema.v2.taxonomies import CPCSlotStatus
from ambiguity_manager.systems.candidate_generation import (
    CRITICAL_SLOTS,
    CandidateInterpretationService,
    candidate_set_fingerprint,
    report_candidate_set,
)
from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput

FIXTURES = Path(__file__).parent / "fixtures" / "t16_t24_synthetic"


def _cpc(**filled: str) -> CPC:
    c = CPC.empty_unknown()
    for key, value in filled.items():
        setattr(c, key, CPCSlot(value=value, status=CPCSlotStatus.FILLED))
    return c


def _candidate(frame_id: str, text: str, **slots: str) -> CandidateInterpretationFrame:
    return CandidateInterpretationFrame(frame_id=frame_id, text=text, cpc=_cpc(**slots))


def _load_cached_analyses() -> dict[str, StructuredAnalysis]:
    payload = json.loads((FIXTURES / "cached_analyses.json").read_text(encoding="utf-8"))
    return {record_id: StructuredAnalysis.from_dict(data) for record_id, data in payload.items()}


def _load_inputs() -> dict[str, SystemInput]:
    rows: dict[str, SystemInput] = {}
    for line in (FIXTURES / "inputs.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = SystemInput.from_dict(json.loads(line))
        rows[payload.record_id] = payload
    return rows


class T17CandidateInterpretationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cached = _load_cached_analyses()
        cls.inputs = _load_inputs()

    def test_unambiguous_fixture_reports_no_findings(self) -> None:
        report = report_candidate_set(self.cached["syn_clear_execute"])

        self.assertEqual(report.findings, [])
        self.assertEqual(report.selected_frame_id, "f1")
        self.assertEqual(report.unresolved_critical_slots, [])

    def test_referential_fixture_retains_unresolved_critical_object(self) -> None:
        report = report_candidate_set(self.cached["syn_referential_clarify"])

        self.assertIn("object", CRITICAL_SLOTS)
        self.assertIn("unresolved_critical_slot:object", report.findings)
        self.assertEqual(report.unresolved_critical_slots, ["object"])

    def test_spatial_fixture_has_stable_candidate_fingerprint(self) -> None:
        analysis = self.cached["syn_spatial_silent"]

        first = candidate_set_fingerprint(analysis.candidate_interpretations)
        second = candidate_set_fingerprint(analysis.candidate_interpretations)

        self.assertEqual(first, second)
        self.assertTrue(first)

    def test_compound_fixture_retains_multiple_unresolved_critical_slots(self) -> None:
        report = report_candidate_set(self.cached["syn_compound_multistep"])

        self.assertEqual(report.unresolved_critical_slots, ["object", "destination"])
        self.assertIn("unresolved_critical_slot:object", report.findings)
        self.assertIn("unresolved_critical_slot:destination", report.findings)

    def test_duplicate_candidate_is_rejected(self) -> None:
        service = CandidateInterpretationService()
        candidates = [
            _candidate("f1", "bring red mug", action="bring", object="red mug"),
            _candidate("f2", "bring red mug", action="bring", object="red mug"),
        ]

        findings = service.validate_candidates(candidates)

        self.assertTrue(any(item.startswith("exact_duplicate_interpretation:") for item in findings))

    def test_materially_different_candidates_are_retained(self) -> None:
        service = CandidateInterpretationService()
        candidates = [
            _candidate("f1", "bring red mug", action="bring", object="red mug"),
            _candidate("f2", "bring blue mug", action="bring", object="blue mug"),
        ]

        findings = service.validate_candidates(candidates)
        analysis = service.build_analysis(candidates=candidates)

        self.assertFalse(any(item.startswith("exact_duplicate_interpretation:") for item in findings))
        self.assertEqual(len(analysis.candidate_interpretations), 2)
        self.assertTrue(analysis.ambiguity_present)

    def test_unsupported_specificity_detected(self) -> None:
        service = CandidateInterpretationService()
        system_input = self.inputs["syn_unsupported_silent"]
        candidate = _candidate("f-purple", "pass purple vase", action="pass", object="purple vase")

        findings = service.detect_unsupported_specificity(candidate, system_input)

        self.assertEqual(findings, ["unsupported_specificity:object=purple vase"])

    def test_selected_candidate_requires_evidence(self) -> None:
        service = CandidateInterpretationService()
        candidates = [_candidate("f1", "pass mug", action="pass", object="mug")]
        selected = SelectedInterpretation(frame_id="f1", supporting_evidence=[])

        findings = service.validate_candidates(candidates, selected=selected)

        self.assertIn("selected_interpretation_missing_evidence", findings)

    def test_missing_evidence_fixture_and_unsupported_specificity_are_both_visible(self) -> None:
        analysis = self.cached["syn_unsupported_silent"]
        report = report_candidate_set(analysis)

        self.assertIn("selected_interpretation_missing_evidence", report.findings)
        self.assertIn("object", report.unresolved_critical_slots)
        self.assertIn("unsupported_specificity:object=purple vase", analysis.unsupported_specificity)

    def test_build_analysis_carries_unresolved_critical_slots(self) -> None:
        service = CandidateInterpretationService()
        analysis = service.build_analysis(
            candidates=[_candidate("f1", "bring mug", action="bring", object="mug")],
            selected=None,
            unresolved=[UnresolvedSlot(slot_name="object", reason="referential")],
            supporting_evidence=[EvidenceRef(source="scene_context", span="red mug, blue mug")],
        )

        self.assertEqual(analysis.unresolved_slots[0].slot_name, "object")
        self.assertIn("unresolved_critical_slot:object", analysis.findings)


if __name__ == "__main__":
    unittest.main()
