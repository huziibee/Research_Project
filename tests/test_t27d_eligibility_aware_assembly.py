from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.model.task_prediction_contract import TaskPredictionResult, load_field_responsibility_registry, load_task_registry
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES, RouteLabel
from ambiguity_manager.systems.contracts import StructuredAnalysis
from ambiguity_manager.systems.structured_analysis_assembler import StructuredAnalysisAssembler


def result(task_id: str, payload: dict, *, accepted: bool = True, version: str = "1.0.0") -> TaskPredictionResult:
    return TaskPredictionResult(
        record_id="t27d:test",
        task_id=task_id,
        task_version=version,
        raw_attempts=("{}",),
        parsed_output=payload if accepted else None,
        transport_status="constrained_generated",
        parse_status="valid" if accepted else "failed",
        schema_status="valid" if accepted else "not_attempted",
        semantic_status="valid" if accepted else "not_attempted",
        safety_status="accepted" if accepted else "rejected",
        final_status="accepted" if accepted else "rejected",
        task_provenance={},
        output_hash=f"hash:{task_id}" if accepted else None,
        constraint_initialised=True,
    )


def cpc() -> dict:
    return {name: {"value": None, "status": "unknown"} for name in CPC_SLOT_NAMES} | {
        "action": {"value": "move", "status": "filled"},
        "object": {"value": "cup", "status": "filled"},
    }


class T27DEligibilityAwareAssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.assembler = StructuredAnalysisAssembler(
            field_registry=load_field_responsibility_registry(ROOT),
            task_registry=load_task_registry(ROOT),
            base_model_identity="base",
            input_hash="input",
        )

    def core(self) -> list[TaskPredictionResult]:
        return [
            result("predict_cpc_v1", {"cpc": cpc()}),
            result("predict_ambiguity_v1", {"ambiguity_present": False, "ambiguity_types": []}),
        ]

    def test_missing_intent_is_partial_and_metric_ineligible(self) -> None:
        out = self.assembler.assemble(record_id="r", task_results=self.core())
        self.assertEqual(out.status, "assembled_complete")
        self.assertTrue(out.production_schema_valid)
        self.assertFalse(out.metric_eligibility["intent"])
        self.assertIsNone(out.analysis.speech_act)

    def test_missing_cpc_is_unknown_and_fail_safe(self) -> None:
        out = self.assembler.assemble(
            record_id="r", task_results=[result("predict_ambiguity_v1", {"ambiguity_present": False, "ambiguity_types": []})]
        )
        self.assertEqual(out.status, "assembled_partial_fail_safe")
        self.assertEqual(out.analysis.cpc.to_dict(), StructuredAnalysis().cpc.to_dict())
        self.assertNotEqual(out.analysis.recommended_strategy, RouteLabel.EXECUTE)

    def test_missing_ambiguity_is_null_not_false(self) -> None:
        out = self.assembler.assemble(record_id="r", task_results=[result("predict_cpc_v1", {"cpc": cpc()})])
        self.assertIsNone(out.analysis.ambiguity_present)
        self.assertIn("ambiguity_prediction_unavailable", out.analysis.findings)
        self.assertNotEqual(out.analysis.recommended_strategy, RouteLabel.EXECUTE)

    def test_missing_optional_tasks_are_fail_safe(self) -> None:
        out = self.assembler.assemble(record_id="r", task_results=self.core())
        self.assertEqual(out.analysis.candidate_interpretations, [])
        self.assertIsNone(out.analysis.selected_interpretation)
        self.assertEqual(out.analysis.risk_level.value, "unknown")
        self.assertEqual(out.analysis.capability_status.value, "unknown")
        self.assertNotEqual(out.analysis.recommended_strategy, RouteLabel.SILENTLY_RESOLVE)

    def test_completeness_round_trip_and_failures(self) -> None:
        out = self.assembler.assemble(record_id="r", task_results=self.core())
        self.assertEqual(StructuredAnalysis.from_dict(out.analysis.to_dict()).to_dict(), out.analysis.to_dict())
        self.assertIn("cpc", out.completeness_map)
        self.assertIn("predict_risk_capability_v1", out.task_states)
        self.assertIn("missing_optional_interpretations_forbid_silent_resolve", out.notes)

    def test_full_bundle_is_complete(self) -> None:
        tasks = self.core() + [
            result("predict_intent_v1", {"intent_summary": "move cup", "speech_act": "directive_command"}),
            result("predict_interpretations_v1", {"candidate_interpretations": []}),
            result("predict_risk_capability_v1", {"risk_relevant": False, "risk_level": "none", "capability_status": "capable"}),
        ]
        out = self.assembler.assemble(record_id="r", task_results=tasks)
        self.assertEqual(out.status, "assembled_complete")
        self.assertTrue(out.semantic_safety_accepted)

    def test_corrupt_and_conflicting_inputs_are_not_partial(self) -> None:
        bad = self.assembler.assemble(record_id="r", task_results=[result("predict_cpc_v1", {"cpc": cpc()}, version="9.9.9")])
        self.assertEqual(bad.status, "unavailable_corrupt_input")
        duplicate = self.assembler.assemble(record_id="r", task_results=self.core() + [self.core()[0]])
        self.assertEqual(duplicate.status, "conflict")


if __name__ == "__main__":
    unittest.main()
