"""T27C assembler-focused tests (complements test_t27c_task_registry_and_assembler)."""

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
    load_field_responsibility_registry,
    load_task_registry,
)
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES, RouteLabel  # noqa: E402
from ambiguity_manager.systems.structured_analysis_assembler import (  # noqa: E402
    StructuredAnalysisAssembler,
)


def _accepted(task_id: str, parsed: dict, version: str = "1.0.0") -> TaskPredictionResult:
    return TaskPredictionResult(
        record_id="test:asm",
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
        output_hash=f"h-{task_id}",
        constraint_initialised=True,
    )


def _cpc() -> dict:
    return {
        name: {"value": None, "status": "unknown"} for name in CPC_SLOT_NAMES
    } | {
        "action": {"value": "bring", "status": "filled"},
        "object": {"value": "cup", "status": "filled"},
    }


class T27CAssemblerExtraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = load_task_registry(ROOT)
        cls.fields = load_field_responsibility_registry(ROOT)

    def _assembler(self, *, variant: str = "full_context", input_hash: str = "in") -> StructuredAnalysisAssembler:
        return StructuredAnalysisAssembler(
            field_registry=self.fields,
            task_registry=self.tasks,
            analysis_variant=variant,
            base_model_identity="base",
            adapter_identity="adapter",
            input_hash=input_hash,
        )

    def _required(self) -> list[TaskPredictionResult]:
        return [
            _accepted(
                "predict_intent_v1",
                {"speech_act": "directive_command", "intent_summary": "bring cup"},
            ),
            _accepted("predict_cpc_v1", {"cpc": _cpc()}),
            _accepted(
                "predict_ambiguity_v1",
                {
                    "ambiguity_present": True,
                    "ambiguity_types": ["referential", "spatial"],
                    "primary_ambiguity_type": "referential",
                },
            ),
        ]

    def test_missing_interpretations_forbid_silent_resolve(self) -> None:
        out = self._assembler().assemble(record_id="test:asm", task_results=self._required())
        self.assertEqual(out.status, "assembled")
        assert out.analysis is not None
        self.assertNotEqual(out.analysis.recommended_strategy, RouteLabel.SILENTLY_RESOLVE)
        self.assertTrue(any("missing_optional_interpretations" in n for n in out.notes))

    def test_content_hash_includes_task_hashes_and_variant(self) -> None:
        a = self._assembler(variant="full_context", input_hash="A")
        b = self._assembler(variant="context_blind", input_hash="A")
        c = self._assembler(variant="full_context", input_hash="B")
        ra = a.assemble(record_id="test:asm", task_results=self._required())
        rb = b.assemble(record_id="test:asm", task_results=self._required())
        rc = c.assemble(record_id="test:asm", task_results=self._required())
        self.assertNotEqual(ra.content_hash, rb.content_hash)
        self.assertNotEqual(ra.content_hash, rc.content_hash)
        self.assertIn("predict_intent_v1", ra.accepted_task_hashes)

    def test_model_cannot_override_route(self) -> None:
        poisoned = self._required()
        # Inject a fake accepted route-like field into intent output — assembler must ignore.
        poisoned[0] = _accepted(
            "predict_intent_v1",
            {
                "speech_act": "directive_command",
                "intent_summary": "x",
            },
        )
        out = self._assembler().assemble(record_id="test:asm", task_results=poisoned)
        assert out.analysis is not None
        self.assertIsNotNone(out.router_decision)
        self.assertTrue(
            any(p.source_kind == "deterministic_rule" for p in out.field_provenance if p.field_path == "recommended_strategy")
        )

    def test_assembly_order_independent(self) -> None:
        req = self._required()
        out1 = self._assembler().assemble(record_id="test:asm", task_results=req)
        out2 = self._assembler().assemble(record_id="test:asm", task_results=list(reversed(req)))
        self.assertEqual(out1.content_hash, out2.content_hash)


if __name__ == "__main__":
    unittest.main()
