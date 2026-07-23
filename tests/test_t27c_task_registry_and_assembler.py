"""T27C focused contract and assembler unit tests (CPU-only)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.model.task_prediction_contract import (  # noqa: E402
    TaskPredictionResult,
    build_task_prediction_request,
    evaluate_task_output,
    load_field_responsibility_registry,
    load_task_registry,
    registry_hash,
    validate_field_responsibility_registry,
    validate_task_registry,
)
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES  # noqa: E402
from ambiguity_manager.systems.structured_analysis_assembler import (  # noqa: E402
    ASSEMBLER_VERSION,
    StructuredAnalysisAssembler,
)


def _accepted_result(task_id: str, parsed: dict, version: str = "1.0.0") -> TaskPredictionResult:
    return TaskPredictionResult(
        record_id="test:1",
        task_id=task_id,
        task_version=version,
        raw_attempts=("{}",),
        parsed_output=parsed,
        transport_status="constrained_generated",
        parse_status="valid",
        schema_status="valid",
        semantic_status="valid",
        safety_status="accepted",
        final_status="accepted",
        task_provenance={},
        output_hash=f"hash-{task_id}",
        constraint_initialised=True,
    )


def _empty_cpc() -> dict:
    return {
        name: {"value": None, "status": "unknown"} for name in CPC_SLOT_NAMES
    } | {"action": {"value": "bring", "status": "filled"}, "object": {"value": "cup", "status": "filled"}}


class T27CTaskRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = load_task_registry(ROOT)
        cls.fields = load_field_responsibility_registry(ROOT)

    def test_unique_task_ids_and_schemas(self) -> None:
        validate_task_registry(self.tasks)
        ids = [t["task_id"] for t in self.tasks["tasks"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 5)
        for task in self.tasks["tasks"]:
            self.assertIn("json_schema", task)
            self.assertTrue(task["prompt_contract_identity"].startswith("t27c_task_prompt_v1/"))

    def test_cpc_uses_production_slots(self) -> None:
        cpc_task = next(t for t in self.tasks["tasks"] if t["task_id"] == "predict_cpc_v1")
        required = cpc_task["json_schema"]["properties"]["cpc"]["required"]
        self.assertEqual(list(required), list(CPC_SLOT_NAMES))

    def test_deterministic_fields_not_model_emitted(self) -> None:
        validate_field_responsibility_registry(self.fields)
        forbidden = set(self.fields["model_must_not_emit"])
        for task in self.tasks["tasks"]:
            owned = set(task["owned_production_fields"])
            self.assertFalse(owned & forbidden)

    def test_registry_hashes_deterministic(self) -> None:
        self.assertEqual(registry_hash(self.tasks), registry_hash(load_task_registry(ROOT)))
        self.assertEqual(registry_hash(self.fields), registry_hash(load_field_responsibility_registry(ROOT)))

    def test_prompt_contains_task_id(self) -> None:
        task = self.tasks["tasks"][0]
        req = build_task_prediction_request(
            record_id="r1",
            task_spec=task,
            command="bring the cup",
            base_model_identity="Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218",
            adapter_identity=None,
            generation_config={"max_new_tokens": 64, "do_sample": False},
        )
        self.assertIn(f"TASK_ID={task['task_id']}", req.model_input)


class T27CAssemblerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = load_task_registry(ROOT)
        cls.fields = load_field_responsibility_registry(ROOT)
        cls.assembler = StructuredAnalysisAssembler(
            field_registry=cls.fields,
            task_registry=cls.tasks,
            analysis_variant="full_context",
            base_model_identity="Qwen/Qwen3-8B@test",
            adapter_identity=None,
            input_hash="input",
        )

    def test_valid_assembly(self) -> None:
        results = [
            _accepted_result(
                "predict_intent_v1",
                {"intent_summary": "bring cup", "speech_act": "directive_command"},
            ),
            _accepted_result("predict_cpc_v1", {"cpc": _empty_cpc()}),
            _accepted_result(
                "predict_ambiguity_v1",
                {
                    "ambiguity_present": True,
                    "ambiguity_types": ["referential"],
                    "primary_ambiguity_type": "referential",
                },
            ),
        ]
        out = self.assembler.assemble(record_id="test:1", task_results=results)
        self.assertEqual(out.status, "assembled")
        self.assertTrue(out.production_schema_valid)
        self.assertIsNotNone(out.analysis)
        assert out.analysis is not None
        self.assertEqual(out.analysis.speech_act, "directive_command")
        self.assertTrue(out.analysis.compound_ambiguity is False)
        self.assertIsNotNone(out.analysis.recommended_strategy)
        self.assertEqual(out.analysis.analysis_provenance.method, "task_conditioned_assembly_v1")
        self.assertEqual(ASSEMBLER_VERSION, "structured_analysis_assembler_v1")

    def test_missing_required_task(self) -> None:
        results = [
            _accepted_result(
                "predict_intent_v1",
                {"intent_summary": "bring cup"},
            ),
            _accepted_result("predict_cpc_v1", {"cpc": _empty_cpc()}),
        ]
        out = self.assembler.assemble(record_id="test:1", task_results=results)
        self.assertEqual(out.status, "unavailable")
        self.assertTrue(any("missing_required_task:predict_ambiguity_v1" in f for f in out.failures))

    def test_missing_risk_becomes_unknown_not_safe(self) -> None:
        results = [
            _accepted_result(
                "predict_intent_v1",
                {"intent_summary": "bring cup"},
            ),
            _accepted_result("predict_cpc_v1", {"cpc": _empty_cpc()}),
            _accepted_result(
                "predict_ambiguity_v1",
                {"ambiguity_present": False, "ambiguity_types": []},
            ),
        ]
        out = self.assembler.assemble(record_id="test:1", task_results=results)
        self.assertEqual(out.status, "assembled")
        assert out.analysis is not None
        self.assertEqual(out.analysis.risk_level.value, "unknown")
        self.assertEqual(out.analysis.capability_status.value, "unknown")
        self.assertNotEqual(out.analysis.recommended_strategy.value, "execute")

    def test_duplicate_task_rejected(self) -> None:
        r = _accepted_result(
            "predict_intent_v1",
            {"intent_summary": "bring cup"},
        )
        out = self.assembler.assemble(
            record_id="test:1",
            task_results=[
                r,
                r,
                _accepted_result("predict_cpc_v1", {"cpc": _empty_cpc()}),
                _accepted_result(
                    "predict_ambiguity_v1",
                    {"ambiguity_present": False, "ambiguity_types": []},
                ),
            ],
        )
        self.assertEqual(out.status, "conflict")

    def test_wrong_version_rejected(self) -> None:
        out = self.assembler.assemble(
            record_id="test:1",
            task_results=[
                _accepted_result(
                    "predict_intent_v1",
                    {"intent_summary": "bring cup"},
                    version="9.9.9",
                ),
                _accepted_result("predict_cpc_v1", {"cpc": _empty_cpc()}),
                _accepted_result(
                    "predict_ambiguity_v1",
                    {"ambiguity_present": False, "ambiguity_types": []},
                ),
            ],
        )
        self.assertEqual(out.status, "unavailable")
        self.assertTrue(any("task_version_mismatch" in f for f in out.failures))

    def test_constraint_required_for_acceptance(self) -> None:
        task = next(t for t in self.tasks["tasks"] if t["task_id"] == "predict_intent_v1")
        req = build_task_prediction_request(
            record_id="r1",
            task_spec=task,
            command="bring the cup",
            base_model_identity="base",
            adapter_identity=None,
            generation_config={"max_new_tokens": 32},
        )
        result = evaluate_task_output(
            request=req,
            task_spec=task,
            raw_text='{"intent_summary":"bring the cup"}',
            constraint_initialised=False,
        )
        self.assertEqual(result.final_status, "rejected")
        self.assertIn("constraint_not_initialised", result.failure_details)


if __name__ == "__main__":
    unittest.main()
