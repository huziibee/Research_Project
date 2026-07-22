"""RED/GREEN regression tests for T16-T24 context-ablation hardening.

These tests encode the intended correct behaviour for context-blind
execution: a context-blind system must never let context-derived resolved
values survive ablation, must record the ablation/input hash in its
provenance, and must never mutate the caller's original ``SystemInput``.
"""

from __future__ import annotations

import unittest

from ambiguity_manager.schema.v2.records import CPC, CPCSlot, EvidenceRef, ResolvedSlotValue, UnresolvedSlot
from ambiguity_manager.schema.v2.taxonomies import AmbiguityType, CapabilityStatus, CPCSlotStatus, RiskLevel
from ambiguity_manager.systems.contracts import AnalysisProvenance, StructuredAnalysis, SystemInput
from ambiguity_manager.systems.context_resolution import ContextResolver
from ambiguity_manager.systems.errors import ContextAblationError
from ambiguity_manager.systems.manager import FullManager
from ambiguity_manager.systems.providers import DeterministicAnalysisProvider
from ambiguity_manager.systems.routing import DeterministicRouter
from ambiguity_manager.systems.safety import SafetyEnforcer
from ambiguity_manager.systems.variants import ContextBlindManagerSystem, FullTypeRiskAwareManagerSystem


def _cpc(**filled: str) -> CPC:
    c = CPC.empty_unknown()
    for key, value in filled.items():
        setattr(c, key, CPCSlot(value=value, status=CPCSlotStatus.FILLED))
    return c


def _resolver() -> ContextResolver:
    return ContextResolver(
        policy={
            "block_silent_resolve_risk_levels": ["medium", "high"],
            "approved_defaults": {},
        }
    )


def _safety() -> SafetyEnforcer:
    return SafetyEnforcer(policy={"enforcement_mode": "fail_closed"})


def _manager(provider: DeterministicAnalysisProvider | None = None) -> FullManager:
    return FullManager(
        analysis_provider=provider,
        router=DeterministicRouter(precedence={"version": "test"}),
        resolver=_resolver(),
        safety=_safety(),
    )


def _full_context_input(record_id: str = "ctx-full-1") -> SystemInput:
    return SystemInput(
        record_id=record_id,
        command="Put the cup on the table.",
        dialogue_history=("user: use the left one",),
        scene_context="objects: cup; destinations: left table",
        capability_context="capable: put",
    )


def _full_context_analysis() -> StructuredAnalysis:
    return StructuredAnalysis(
        speech_act="directive_command",
        cpc=_cpc(action="put", object="cup"),
        unresolved_slots=[],
        resolved_slots=[ResolvedSlotValue(slot_name="destination", value="left table")],
        resolution_evidence=[
            EvidenceRef(source="scene_context", span="left table", note="unique_destination")
        ],
        resolution_method="deterministic_context_resolution_v1",
        ambiguity_types=[AmbiguityType.SPATIAL],
        ambiguity_present=True,
        risk_level=RiskLevel.LOW,
        capability_status=CapabilityStatus.CAPABLE,
        analysis_provenance=AnalysisProvenance(provider_id="full_context_provider", method="full_context"),
    )


class T16T24ContextAblationHardeningTests(unittest.TestCase):
    def test_full_context_cached_analysis_is_rejected_or_stripped(self) -> None:
        system = ContextBlindManagerSystem(inner=_manager())
        result = system.run(_full_context_input(), cached_analysis=_full_context_analysis())
        destination_values = [
            r.value for r in result.analysis.resolved_slots if r.slot_name == "destination"
        ]
        self.assertNotIn("left table", destination_values)
        self.assertTrue(
            result.runtime_metadata.get("context_ablation", {}).get("rejected_full_context_cache")
            or result.runtime_metadata.get("context_ablation", {}).get(
                "stripped_context_derived_fields"
            )
        )

    def test_context_derived_resolved_slot_cannot_survive_ablation(self) -> None:
        # With a provider, full-context cache is rejected and a fresh ablated analysis is used.
        record_id = "ctx-survive-1"
        base = StructuredAnalysis(
            speech_act="directive_command",
            cpc=_cpc(action="put", object="cup"),
            unresolved_slots=[UnresolvedSlot(slot_name="destination", reason="missing")],
            ambiguity_types=[AmbiguityType.SPATIAL],
            ambiguity_present=True,
            risk_level=RiskLevel.LOW,
            capability_status=CapabilityStatus.CAPABLE,
        )
        provider = DeterministicAnalysisProvider({record_id: base})
        system = ContextBlindManagerSystem(analysis_provider=provider, inner=_manager(provider))
        result = system.run(_full_context_input(record_id), cached_analysis=_full_context_analysis())
        destination_values = [
            r.value for r in result.analysis.resolved_slots if r.slot_name == "destination"
        ]
        self.assertNotIn("left table", destination_values)
        evidence_sources = [e.source for e in result.analysis.resolution_evidence]
        self.assertNotIn("scene_context", evidence_sources)

    def test_matching_context_blind_cache_is_accepted(self) -> None:
        full_input = _full_context_input()
        blinded = full_input.without_context()
        ablation_hash = blinded.fingerprint()
        context_blind_analysis = StructuredAnalysis(
            speech_act="directive_command",
            cpc=_cpc(action="put", object="cup"),
            unresolved_slots=[UnresolvedSlot(slot_name="destination", reason="context_blind_no_scene")],
            resolved_slots=[],
            risk_level=RiskLevel.LOW,
            capability_status=CapabilityStatus.CAPABLE,
            analysis_provenance=AnalysisProvenance(
                provider_id="context_blind_cache",
                method="context_blind",
                notes=f"ablated_input_hash={ablation_hash}",
            ),
        )
        system = ContextBlindManagerSystem(inner=_manager())
        result = system.run(full_input, cached_analysis=context_blind_analysis)
        self.assertEqual(result.execution_status, "ok")

    def test_ablation_input_hash_is_recorded_in_result_provenance(self) -> None:
        full_input = _full_context_input()
        blinded = full_input.without_context()
        ablation_hash = blinded.fingerprint()
        context_blind_analysis = StructuredAnalysis(
            speech_act="directive_command",
            cpc=_cpc(action="put", object="cup"),
            unresolved_slots=[UnresolvedSlot(slot_name="destination", reason="context_blind_no_scene")],
            resolved_slots=[],
            risk_level=RiskLevel.LOW,
            capability_status=CapabilityStatus.CAPABLE,
            analysis_provenance=AnalysisProvenance(
                provider_id="context_blind_cache",
                method="context_blind",
                notes=f"ablated_input_hash={ablation_hash}",
            ),
        )
        system = ContextBlindManagerSystem(inner=_manager())
        result = system.run(full_input, cached_analysis=context_blind_analysis)
        recorded = result.runtime_metadata.get("context_ablation", {})
        self.assertEqual(recorded.get("ablated_input_hash"), ablation_hash)

    def test_original_system_input_unchanged_after_context_blind_run(self) -> None:
        original = _full_context_input()
        blinded = original.without_context()
        ablation_hash = blinded.fingerprint()
        context_blind_analysis = StructuredAnalysis(
            speech_act="directive_command",
            cpc=_cpc(action="put", object="cup"),
            unresolved_slots=[UnresolvedSlot(slot_name="destination", reason="context_blind_no_scene")],
            risk_level=RiskLevel.LOW,
            capability_status=CapabilityStatus.CAPABLE,
            analysis_provenance=AnalysisProvenance(
                provider_id="context_blind_cache",
                method="context_blind",
                notes=f"ablated_input_hash={ablation_hash}",
            ),
        )
        system = ContextBlindManagerSystem(inner=_manager())
        system.run(original, cached_analysis=context_blind_analysis)
        self.assertEqual(original.scene_context, "objects: cup; destinations: left table")
        self.assertEqual(original.capability_context, "capable: put")
        self.assertEqual(original.dialogue_history, ("user: use the left one",))

    def test_context_blind_and_full_manager_use_distinct_analysis_identities_when_context_matters(
        self,
    ) -> None:
        record_id = "ctx-distinct-1"
        base_analysis = StructuredAnalysis(
            speech_act="directive_command",
            cpc=_cpc(action="put", object="cup"),
            unresolved_slots=[UnresolvedSlot(slot_name="destination", reason="spatial")],
            ambiguity_types=[AmbiguityType.SPATIAL],
            ambiguity_present=True,
            risk_level=RiskLevel.LOW,
            capability_status=CapabilityStatus.CAPABLE,
        )
        provider = DeterministicAnalysisProvider({record_id: base_analysis})
        full_input = _full_context_input(record_id)

        full_system = FullTypeRiskAwareManagerSystem(manager=_manager(provider))
        blind_system = ContextBlindManagerSystem(analysis_provider=provider, inner=_manager(provider))

        full_result = full_system.run(full_input)
        blind_result = blind_system.run(full_input)

        self.assertNotEqual(full_result.analysis.fingerprint(), blind_result.analysis.fingerprint())
        self.assertNotEqual(full_result.result_hash, blind_result.result_hash)


if __name__ == "__main__":
    unittest.main()
