"""RED/GREEN regression tests for T16-T24 context-ablation hardening.

A context-blind system may use only:
  A. a fresh analysis produced from the ablated SystemInput; or
  B. a cached analysis whose canonical input identity exactly matches the
     ablated input and whose provenance explicitly identifies the
     context-blind variant.

It must never sanitise and reuse a full-context semantic analysis.
"""

from __future__ import annotations

import copy
import unittest

from ambiguity_manager.schema.v2.records import (
    CPC,
    CPCSlot,
    CandidateInterpretationFrame,
    EvidenceRef,
    ResolvedSlotValue,
    SelectedInterpretation,
    UnresolvedSlot,
)
from ambiguity_manager.schema.v2.taxonomies import (
    AmbiguityType,
    CapabilityStatus,
    CPCSlotStatus,
    RiskLevel,
)
from ambiguity_manager.systems.analysis import (
    build_analysis_identity,
    validate_context_blind_cache,
)
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


def _adversarial_input(record_id: str = "ctx-pick-red-cup") -> SystemInput:
    return SystemInput(
        record_id=record_id,
        command="Pick it up.",
        dialogue_history=("user: the red one please",),
        scene_context="user pointed to the red cup",
        capability_context="capable: pick",
    )


def _adversarial_full_context_analysis() -> StructuredAnalysis:
    return StructuredAnalysis(
        speech_act="directive_command",
        intent_summary="pick up the red cup (from scene pointing)",
        cpc=_cpc(action="pick", object="red cup"),
        candidate_interpretations=[
            CandidateInterpretationFrame(
                frame_id="red_cup",
                text="red cup from pointing gesture",
                cpc=_cpc(action="pick", object="red cup"),
            )
        ],
        selected_interpretation=SelectedInterpretation(
            frame_id="red_cup",
            supporting_evidence=[
                EvidenceRef(source="scene_context", span="red cup", note="pointing_gesture")
            ],
        ),
        unresolved_slots=[],
        resolved_slots=[ResolvedSlotValue(slot_name="object", value="red cup")],
        supporting_evidence=[
            EvidenceRef(source="scene_context", span="red cup", note="pointing_gesture")
        ],
        resolution_evidence=[
            EvidenceRef(source="scene_context", span="red cup", note="pointing_gesture")
        ],
        resolution_method="full_context_resolution",
        ambiguity_types=[AmbiguityType.REFERENTIAL],
        ambiguity_present=True,
        primary_ambiguity_type=AmbiguityType.REFERENTIAL,
        risk_level=RiskLevel.LOW,
        risk_relevant=False,
        capability_status=CapabilityStatus.CAPABLE,
        analysis_provenance=AnalysisProvenance(
            provider_id="full_context_provider",
            method="full_context",
            notes="derived_from_scene_pointing",
        ),
    )


def _matching_context_blind_analysis(ablated_input: SystemInput) -> StructuredAnalysis:
    ablated_hash = ablated_input.fingerprint()
    return StructuredAnalysis(
        speech_act="directive_command",
        cpc=_cpc(action="pick"),
        unresolved_slots=[UnresolvedSlot(slot_name="object", reason="context_blind_no_scene")],
        resolved_slots=[],
        supporting_evidence=[],
        ambiguity_types=[AmbiguityType.REFERENTIAL],
        ambiguity_present=True,
        risk_level=RiskLevel.LOW,
        capability_status=CapabilityStatus.CAPABLE,
        analysis_provenance=AnalysisProvenance(
            provider_id="context_blind_cache",
            provider_version="1.0.0",
            analysis_id=ablated_hash,
            method="context_blind",
            notes=f"ablated_input_hash={ablated_hash}",
        ),
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
    def test_full_context_cached_analysis_is_rejected(self) -> None:
        """Full-context cache must be rejected completely — never sanitised/reused."""
        system = ContextBlindManagerSystem(inner=_manager())
        result = system.run(
            _adversarial_input(),
            cached_analysis=_adversarial_full_context_analysis(),
        )
        self.assertIn(result.execution_status, {"provider_unavailable", "not_executable"})
        ablation = result.runtime_metadata.get("context_ablation", {})
        self.assertTrue(ablation.get("rejected_full_context_cache"))
        self.assertFalse(ablation.get("stripped_context_derived_fields", False))

        # No full-context semantic values may survive.
        self.assertNotEqual(
            (result.analysis.cpc.object.value or "").lower(),
            "red cup",
        )
        self.assertIsNone(result.analysis.selected_interpretation)
        self.assertEqual(result.analysis.candidate_interpretations, [])
        evidence_sources = [e.source for e in result.analysis.supporting_evidence]
        self.assertNotIn("scene_context", evidence_sources)
        self.assertNotIn(
            "red cup",
            [r.value for r in result.analysis.resolved_slots],
        )
        # Must not execute a stripped/sanitised full-context analysis.
        self.assertNotEqual(result.execution_status, "ok")

    def test_full_context_semantic_values_cannot_survive_ablation(self) -> None:
        system = ContextBlindManagerSystem(inner=_manager())
        result = system.run(
            _adversarial_input(),
            cached_analysis=_adversarial_full_context_analysis(),
        )
        payload = result.analysis.to_dict()
        blob = str(payload).lower()
        self.assertNotIn("red cup", blob)
        self.assertNotIn("pointing", blob)
        self.assertNotIn("scene_context", blob)

    def test_matching_context_blind_cache_is_accepted(self) -> None:
        full_input = _adversarial_input()
        blinded = full_input.without_context()
        context_blind_analysis = _matching_context_blind_analysis(blinded)
        system = ContextBlindManagerSystem(inner=_manager())
        result = system.run(full_input, cached_analysis=context_blind_analysis)
        self.assertEqual(result.execution_status, "ok")
        ablation = result.runtime_metadata.get("context_ablation", {})
        self.assertFalse(ablation.get("rejected_full_context_cache", False))
        self.assertEqual(
            [u.slot_name for u in result.analysis.unresolved_slots],
            ["object"],
        )

    def test_fresh_provider_analysis_from_ablated_input_is_accepted(self) -> None:
        record_id = "ctx-fresh-1"
        full_input = _adversarial_input(record_id)
        ablated = full_input.without_context()
        fresh = StructuredAnalysis(
            speech_act="directive_command",
            cpc=_cpc(action="pick"),
            unresolved_slots=[UnresolvedSlot(slot_name="object", reason="no_context")],
            ambiguity_present=True,
            ambiguity_types=[AmbiguityType.REFERENTIAL],
            risk_level=RiskLevel.LOW,
            capability_status=CapabilityStatus.CAPABLE,
        )
        provider = DeterministicAnalysisProvider({record_id: fresh})
        system = ContextBlindManagerSystem(analysis_provider=provider, inner=_manager(provider))
        result = system.run(full_input)
        self.assertEqual(result.execution_status, "ok")
        self.assertNotIn("red cup", str(result.analysis.to_dict()).lower())
        # Ablated input hash must be recorded.
        self.assertEqual(
            result.runtime_metadata["context_ablation"]["ablated_input_hash"],
            ablated.fingerprint(),
        )

    def test_provider_receives_ablated_input_not_original(self) -> None:
        record_id = "ctx-provider-ablated"
        full_input = _adversarial_input(record_id)
        seen: list[SystemInput] = []

        class CapturingProvider:
            provider_id = "capturing"
            provider_version = "1.0.0"

            def analyse(self, system_input: SystemInput) -> StructuredAnalysis:
                seen.append(system_input)
                return StructuredAnalysis(
                    speech_act="directive_command",
                    cpc=_cpc(action="pick"),
                    unresolved_slots=[UnresolvedSlot(slot_name="object", reason="ablated")],
                    risk_level=RiskLevel.LOW,
                    capability_status=CapabilityStatus.CAPABLE,
                )

        system = ContextBlindManagerSystem(
            analysis_provider=CapturingProvider(),
            inner=_manager(),
        )
        system.run(full_input, cached_analysis=_adversarial_full_context_analysis())
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].command, "Pick it up.")
        self.assertEqual(seen[0].dialogue_history, ())
        self.assertIsNone(seen[0].scene_context)
        self.assertIsNone(seen[0].capability_context)

    def test_original_system_input_unchanged_after_context_blind_run(self) -> None:
        original = _adversarial_input()
        snapshot = original.to_dict()
        blinded = original.without_context()
        system = ContextBlindManagerSystem(inner=_manager())
        system.run(original, cached_analysis=_matching_context_blind_analysis(blinded))
        self.assertEqual(original.to_dict(), snapshot)
        self.assertEqual(original.scene_context, "user pointed to the red cup")
        self.assertEqual(original.capability_context, "capable: pick")
        self.assertEqual(original.dialogue_history, ("user: the red one please",))

    def test_full_context_and_ablated_cache_identities_differ(self) -> None:
        full_input = _adversarial_input()
        ablated = full_input.without_context()
        full_analysis = _adversarial_full_context_analysis()
        blind_analysis = _matching_context_blind_analysis(ablated)
        full_id = build_analysis_identity(
            record_id=full_input.record_id,
            source_input=full_input,
            analysis=full_analysis,
            analysis_variant="full_context",
        )
        blind_id = build_analysis_identity(
            record_id=full_input.record_id,
            source_input=ablated,
            analysis=blind_analysis,
            analysis_variant="context_blind",
        )
        self.assertNotEqual(full_id.fingerprint(), blind_id.fingerprint())
        self.assertNotEqual(full_id.source_input_hash, blind_id.source_input_hash)
        self.assertEqual(full_id.analysis_variant, "full_context")
        self.assertEqual(blind_id.analysis_variant, "context_blind")

    def test_matching_ablated_cache_with_wrong_input_hash_is_rejected(self) -> None:
        full_input = _adversarial_input()
        ablated = full_input.without_context()
        wrong = _matching_context_blind_analysis(ablated)
        wrong.analysis_provenance.notes = "ablated_input_hash=deadbeef" * 2
        wrong.analysis_provenance.analysis_id = "deadbeef" * 4
        with self.assertRaises(ContextAblationError):
            validate_context_blind_cache(wrong, ablated_input=ablated)
        system = ContextBlindManagerSystem(inner=_manager())
        result = system.run(full_input, cached_analysis=wrong)
        self.assertIn(result.execution_status, {"provider_unavailable", "not_executable"})

    def test_matching_hash_with_wrong_variant_is_rejected(self) -> None:
        full_input = _adversarial_input()
        ablated = full_input.without_context()
        ablated_hash = ablated.fingerprint()
        wrong_variant = StructuredAnalysis(
            speech_act="directive_command",
            cpc=_cpc(action="pick"),
            unresolved_slots=[UnresolvedSlot(slot_name="object", reason="missing")],
            risk_level=RiskLevel.LOW,
            capability_status=CapabilityStatus.CAPABLE,
            analysis_provenance=AnalysisProvenance(
                provider_id="full_context_provider",
                method="full_context",
                analysis_id=ablated_hash,
                notes=f"ablated_input_hash={ablated_hash}",
            ),
        )
        with self.assertRaises(ContextAblationError):
            validate_context_blind_cache(wrong_variant, ablated_input=ablated)
        system = ContextBlindManagerSystem(inner=_manager())
        result = system.run(full_input, cached_analysis=wrong_variant)
        self.assertIn(result.execution_status, {"provider_unavailable", "not_executable"})

    def test_absence_of_provider_and_ablated_cache_returns_honest_not_executable(self) -> None:
        system = ContextBlindManagerSystem(inner=_manager())
        result = system.run(
            _adversarial_input(),
            cached_analysis=_adversarial_full_context_analysis(),
        )
        self.assertIn(result.execution_status, {"provider_unavailable", "not_executable"})
        self.assertTrue(
            result.runtime_metadata.get("context_ablation", {}).get("rejected_full_context_cache")
        )

    def test_system_execution_order_cannot_create_cache_leakage(self) -> None:
        record_id = "ctx-order-1"
        full_input = _adversarial_input(record_id)
        ablated = full_input.without_context()
        shared_cache = _adversarial_full_context_analysis()
        cache_before = copy.deepcopy(shared_cache)

        blind = ContextBlindManagerSystem(inner=_manager())
        full = FullTypeRiskAwareManagerSystem(manager=_manager())

        # Blind first (must reject), then full (may use full-context cache).
        blind_result = blind.run(full_input, cached_analysis=shared_cache)
        full_result = full.run(full_input, cached_analysis=shared_cache)
        # Reverse order
        full_result_2 = full.run(full_input, cached_analysis=shared_cache)
        blind_result_2 = blind.run(full_input, cached_analysis=shared_cache)

        self.assertEqual(shared_cache.to_dict(), cache_before.to_dict())
        self.assertIn(blind_result.execution_status, {"provider_unavailable", "not_executable"})
        self.assertIn(blind_result_2.execution_status, {"provider_unavailable", "not_executable"})
        self.assertEqual(full_result.execution_status, "ok")
        self.assertEqual(full_result_2.execution_status, "ok")
        # Blind must not leak red-cup semantics even after full manager ran.
        self.assertNotIn("red cup", str(blind_result.analysis.to_dict()).lower())
        self.assertNotIn("red cup", str(blind_result_2.analysis.to_dict()).lower())
        # Matching ablated cache still works after order games.
        ok = blind.run(full_input, cached_analysis=_matching_context_blind_analysis(ablated))
        self.assertEqual(ok.execution_status, "ok")

    def test_context_derived_resolved_slot_cannot_survive_ablation(self) -> None:
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

    def test_ablation_input_hash_is_recorded_in_result_provenance(self) -> None:
        full_input = _adversarial_input()
        blinded = full_input.without_context()
        system = ContextBlindManagerSystem(inner=_manager())
        result = system.run(full_input, cached_analysis=_matching_context_blind_analysis(blinded))
        recorded = result.runtime_metadata.get("context_ablation", {})
        self.assertEqual(recorded.get("ablated_input_hash"), blinded.fingerprint())

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
