from __future__ import annotations

import copy
import unittest

from ambiguity_manager.schema.v2.records import (
    CPC,
    CPCSlot,
    EvidenceRef,
    LabelEligibility,
    SelectedInterpretation,
)
from ambiguity_manager.schema.v2.taxonomies import CPCSlotStatus, RouteLabel
from ambiguity_manager.systems.contracts import (
    InputProvenance,
    StructuredAnalysis,
    SystemInput,
    SystemResult,
)
from ambiguity_manager.systems.errors import ProviderUnavailableError, SystemsContractError
from ambiguity_manager.systems.providers import (
    DeterministicAnalysisProvider,
    UnavailableProvider,
    require_provider,
)


def _cpc(**filled: str) -> CPC:
    c = CPC.empty_unknown()
    for key, value in filled.items():
        setattr(c, key, CPCSlot(value=value, status=CPCSlotStatus.FILLED))
    return c


class T16ContractsAndProvidersTests(unittest.TestCase):
    def test_valid_contract_objects_round_trip(self) -> None:
        system_input = SystemInput.from_dict(
            {
                "record_id": "rec-1",
                "command": "Pick up the red mug.",
                "dialogue_history": ["user: please do it"],
                "scene_context": "objects: red mug",
                "capability_context": "capable: pick",
                "input_provenance": {
                    "source": "synthetic",
                    "source_dataset": "t16",
                    "source_id": "1",
                    "notes": "unit-test",
                },
                "label_eligibility": LabelEligibility(routing=True, risk=True).to_dict(),
                "extra": {"seed": 7},
            }
        )
        analysis = StructuredAnalysis.from_dict(
            {
                "speech_act": "directive_command",
                "intent_summary": "pick red mug",
                "cpc": _cpc(action="pick", object="red mug").to_dict(),
                "candidate_interpretations": [
                    {
                        "frame_id": "f1",
                        "text": "pick red mug",
                        "cpc": _cpc(action="pick", object="red mug").to_dict(),
                    }
                ],
                "selected_interpretation": {
                    "frame_id": "f1",
                    "supporting_evidence": [{"source": "command", "span": "red mug"}],
                },
                "supporting_evidence": [{"source": "command", "span": "Pick up the red mug."}],
                "recommended_strategy": "execute",
            }
        )
        result = SystemResult.from_dict(
            {
                "record_id": system_input.record_id,
                "system_id": "full_type_risk_aware_manager",
                "system_version": "1.0.0",
                "analysis": analysis.to_dict(),
                "recommended_strategy": "execute",
                "execution_status": "ok",
                "provider_provenance": {"provider_id": "deterministic_analysis"},
                "runtime_metadata": {"router_trace": {"matched_rule_id": "clear_safe_capable"}},
                "synthetic_only": True,
                "official_result": False,
            }
        )

        self.assertEqual(system_input.input_provenance.source, "synthetic")
        self.assertEqual(analysis.selected_interpretation.frame_id, "f1")
        self.assertEqual(result.recommended_strategy, RouteLabel.EXECUTE)
        self.assertEqual(result.execution_status, "ok")
        self.assertEqual(result.to_dict()["record_id"], "rec-1")
        self.assertTrue(result.result_hash)

    def test_invalid_enum_rejected(self) -> None:
        with self.assertRaises(SystemsContractError):
            StructuredAnalysis.from_dict({"speech_act": "not_a_real_intent"})

    def test_result_hash_is_deterministic(self) -> None:
        analysis = StructuredAnalysis(
            speech_act="directive_command",
            cpc=_cpc(action="pick", object="red mug"),
        )
        base_payload = {
            "record_id": "rec-1",
            "system_id": "always_execute",
            "system_version": "1.0.0",
            "analysis": analysis.to_dict(),
            "recommended_strategy": "execute",
            "execution_status": "ok",
        }

        first = SystemResult.from_dict(copy.deepcopy(base_payload))
        second = SystemResult.from_dict(copy.deepcopy(base_payload))

        self.assertEqual(first.compute_hash(), second.compute_hash())
        self.assertEqual(first.result_hash, second.result_hash)
        self.assertEqual(first.to_dict()["result_hash"], second.to_dict()["result_hash"])

    def test_optional_null_behaviour_round_trips(self) -> None:
        system_input = SystemInput.from_dict(
            {
                "record_id": "rec-null",
                "command": "Stop.",
                "dialogue_history": [],
                "scene_context": None,
                "capability_context": None,
                "input_provenance": None,
                "label_eligibility": None,
                "extra": None,
            }
        )
        analysis = StructuredAnalysis.from_dict(
            {
                "speech_act": None,
                "intent_summary": None,
                "cpc": {},
                "selected_interpretation": None,
                "context_sampling_uncertainty": None,
                "recommended_strategy": None,
                "rejection_reason": None,
                "resolution_method": None,
            }
        )
        result = SystemResult.from_dict(
            {
                "record_id": "rec-null",
                "system_id": "direct_base_llm",
                "system_version": "1.0.0",
                "analysis": analysis.to_dict(),
                "recommended_strategy": None,
                "execution_status": "provider_unavailable",
                "clarification_question": None,
                "rejection_reason": None,
            }
        )

        self.assertIsNone(system_input.scene_context)
        self.assertIsNone(system_input.capability_context)
        self.assertEqual(system_input.input_provenance, InputProvenance(source="unspecified"))
        self.assertEqual(system_input.extra, {})
        self.assertIsNone(analysis.recommended_strategy)
        self.assertIsNone(result.recommended_strategy)

    def test_without_context_does_not_mutate_original_input(self) -> None:
        original = SystemInput(
            record_id="rec-ctx",
            command="Fetch the book.",
            dialogue_history=("user: the blue one",),
            scene_context="objects: book",
            capability_context="capable: fetch",
            extra={"nested": {"kept": True}},
        )

        blinded = original.without_context()

        self.assertEqual(original.dialogue_history, ("user: the blue one",))
        self.assertEqual(original.scene_context, "objects: book")
        self.assertEqual(original.capability_context, "capable: fetch")
        self.assertEqual(original.extra, {"nested": {"kept": True}})
        self.assertEqual(blinded.dialogue_history, ())
        self.assertIsNone(blinded.scene_context)
        self.assertIsNone(blinded.capability_context)
        self.assertTrue(blinded.extra["context_ablation"]["scene_context_removed"])

    def test_missing_provider_raises_provider_unavailable(self) -> None:
        with self.assertRaises(ProviderUnavailableError):
            require_provider(None, "StructuredAnalysisProvider")

        provider = UnavailableProvider("DirectLLMProvider")
        with self.assertRaises(ProviderUnavailableError):
            provider.analyse(SystemInput(record_id="rec-1", command="Do it."))

    def test_deterministic_provider_returns_expected_analysis(self) -> None:
        analysis = StructuredAnalysis(
            speech_act="directive_command",
            cpc=_cpc(action="pick", object="red mug"),
            selected_interpretation=SelectedInterpretation(
                frame_id="f1",
                supporting_evidence=[EvidenceRef(source="command", span="red mug")],
            ),
        )
        provider = DeterministicAnalysisProvider({"rec-1": analysis})

        returned = provider.analyse(SystemInput(record_id="rec-1", command="Pick up the red mug."))

        # The provider must hand back a deep copy, not the stored instance,
        # so a caller mutating the returned analysis cannot corrupt the
        # provider's cache for later callers. Compare by content instead.
        self.assertIsNot(returned, analysis)
        self.assertEqual(returned.fingerprint(), analysis.fingerprint())
        self.assertEqual(returned.to_dict(), analysis.to_dict())
        with self.assertRaises(ProviderUnavailableError):
            provider.analyse(SystemInput(record_id="missing", command="Unknown"))


if __name__ == "__main__":
    unittest.main()
