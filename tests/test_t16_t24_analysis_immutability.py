"""RED/GREEN regression tests for T16-T24 analysis immutability hardening.

``StructuredAnalysis`` objects are shared across providers, caches and
multiple comparison systems. This suite locks in the intended contract:
running a system must never mutate a provider-held or caller-supplied
analysis, execution order must not change outputs, repeated execution must
be idempotent, and one system must never contaminate another system's view
of a cached analysis.

``DeterministicAnalysisProvider`` is expected to return deep copies after
the fix, so tests assert content equality (fingerprint/dict equality)
rather than object identity for provider returns.
"""

from __future__ import annotations

import unittest

from ambiguity_manager.schema.v2.records import CPC, CPCSlot, ResolvedSlotValue, UnresolvedSlot
from ambiguity_manager.schema.v2.taxonomies import CapabilityStatus, CPCSlotStatus, RiskLevel
from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput
from ambiguity_manager.systems.context_resolution import ContextResolver
from ambiguity_manager.systems.manager import FullManager
from ambiguity_manager.systems.providers import DeterministicAnalysisProvider
from ambiguity_manager.systems.routing import DeterministicRouter
from ambiguity_manager.systems.safety import SafetyEnforcer
from ambiguity_manager.systems.variants import (
    AlwaysExecuteSystem,
    ContextBlindManagerSystem,
    FullTypeRiskAwareManagerSystem,
)


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


def _fresh_analysis() -> StructuredAnalysis:
    return StructuredAnalysis(
        cpc=_cpc(action="pick", object="mug"),
        unresolved_slots=[UnresolvedSlot(slot_name="destination", reason="spatial")],
        risk_level=RiskLevel.LOW,
        capability_status=CapabilityStatus.CAPABLE,
    )


def _fresh_provider_and_input(record_id: str) -> tuple[DeterministicAnalysisProvider, SystemInput]:
    provider = DeterministicAnalysisProvider({record_id: _fresh_analysis()})
    system_input = SystemInput(
        record_id=record_id,
        command="Pick up the mug.",
        scene_context="destinations: left table",
    )
    return provider, system_input


class T16T24AnalysisImmutabilityTests(unittest.TestCase):
    def test_provider_held_analysis_unchanged_after_full_manager_run(self) -> None:
        analysis = _fresh_analysis()
        fingerprint_before = analysis.fingerprint()
        provider = DeterministicAnalysisProvider({"rec-1": analysis})
        manager = _manager(provider)
        system_input = SystemInput(
            record_id="rec-1",
            command="Pick up the mug.",
            scene_context="destinations: left table",
        )

        manager.run(system_input)

        self.assertEqual(
            provider.analyses_by_record["rec-1"].fingerprint(),
            fingerprint_before,
            msg="the provider's stored analysis must not be mutated by a manager run",
        )

    def test_deterministic_provider_returns_content_equal_copies(self) -> None:
        analysis = _fresh_analysis()
        provider = DeterministicAnalysisProvider({"rec-1": analysis})
        system_input = SystemInput(record_id="rec-1", command="Pick up the mug.")

        returned = provider.analyse(system_input)

        self.assertIsNot(returned, analysis)
        self.assertEqual(returned.fingerprint(), analysis.fingerprint())
        self.assertEqual(returned.to_dict(), analysis.to_dict())

    def test_supplied_cached_analysis_unchanged_after_manager_run(self) -> None:
        cached = _fresh_analysis()
        fingerprint_before = cached.fingerprint()
        manager = _manager(None)
        system_input = SystemInput(
            record_id="rec-2",
            command="Pick up the mug.",
            scene_context="destinations: left table",
        )

        manager.run(system_input, cached_analysis=cached)

        self.assertEqual(
            cached.fingerprint(),
            fingerprint_before,
            msg="a caller-supplied cached analysis must not be mutated in place by manager.run",
        )

    def test_running_systems_in_different_orders_produces_identical_outputs(self) -> None:
        provider_a, input_a = _fresh_provider_and_input("rec-order")
        full_a = FullTypeRiskAwareManagerSystem(manager=_manager(provider_a))
        blind_a = ContextBlindManagerSystem(analysis_provider=provider_a, inner=_manager(provider_a))
        result_full_first = full_a.run(input_a)
        result_blind_first = blind_a.run(input_a)

        provider_b, input_b = _fresh_provider_and_input("rec-order")
        full_b = FullTypeRiskAwareManagerSystem(manager=_manager(provider_b))
        blind_b = ContextBlindManagerSystem(analysis_provider=provider_b, inner=_manager(provider_b))
        result_blind_second = blind_b.run(input_b)
        result_full_second = full_b.run(input_b)

        self.assertEqual(
            result_full_first.result_hash,
            result_full_second.result_hash,
            msg="full_type_risk_aware_manager output must not depend on execution order",
        )
        self.assertEqual(
            result_blind_first.result_hash,
            result_blind_second.result_hash,
            msg="context_blind_manager output must not depend on execution order",
        )

    def test_repeated_execution_produces_identical_hashes(self) -> None:
        provider, system_input = _fresh_provider_and_input("rec-repeat")
        manager = _manager(provider)

        first = manager.run(system_input)
        second = manager.run(system_input)

        self.assertEqual(
            first.result_hash,
            second.result_hash,
            msg="running the same manager on the same input twice must produce identical results",
        )

    def test_one_system_cannot_contaminate_another_systems_cached_analysis(self) -> None:
        cached = _fresh_analysis()
        fingerprint_before = cached.fingerprint()
        system_input = SystemInput(
            record_id="rec-contam",
            command="Pick up the mug.",
            scene_context="destinations: left table",
        )

        manager = _manager(None)
        manager.run(system_input, cached_analysis=cached)

        self.assertEqual(
            cached.fingerprint(),
            fingerprint_before,
            msg="an unrelated manager run must not mutate a shared cached analysis object",
        )

        always_execute = AlwaysExecuteSystem()
        result2 = always_execute.run(system_input, cached_analysis=cached)

        self.assertEqual(
            [u.slot_name for u in result2.analysis.unresolved_slots],
            ["destination"],
            msg="a second system consuming the same cached analysis must see it unresolved, not contaminated",
        )


if __name__ == "__main__":
    unittest.main()
