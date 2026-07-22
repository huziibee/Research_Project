from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from ambiguity_manager.schema.v2.records import ContextSamplingUncertainty
from ambiguity_manager.schema.v2.taxonomies import RiskLevel, RouteLabel
from ambiguity_manager.systems.context_resolution import ContextResolver
from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput
from ambiguity_manager.systems.manager import FullManager
from ambiguity_manager.systems.providers import DeterministicAnalysisProvider
from ambiguity_manager.systems.routing import DeterministicRouter
from ambiguity_manager.systems.safety import SafetyEnforcer
from ambiguity_manager.systems.variants import (
    SYSTEM_IDS,
    AlwaysClarifySystem,
    AlwaysExecuteSystem,
    AlwaysSilentlyResolveSystem,
    ContextBlindManagerSystem,
    DegreeBasedRouterSystem,
    DirectBaseLLMSystem,
    build_default_registry,
    get_system,
    list_systems,
)

FIXTURES = Path(__file__).parent / "fixtures" / "t16_t24_synthetic"


def _load_inputs() -> dict[str, SystemInput]:
    rows: dict[str, SystemInput] = {}
    for line in (FIXTURES / "inputs.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = SystemInput.from_dict(json.loads(line))
        rows[item.record_id] = item
    return rows


def _load_cached() -> dict[str, StructuredAnalysis]:
    payload = json.loads((FIXTURES / "cached_analyses.json").read_text(encoding="utf-8"))
    return {record_id: StructuredAnalysis.from_dict(data) for record_id, data in payload.items()}


def _manager(provider: DeterministicAnalysisProvider) -> FullManager:
    return FullManager(
        analysis_provider=provider,
        router=DeterministicRouter(precedence={"version": "test"}),
        resolver=ContextResolver(
            policy={
                "block_silent_resolve_risk_levels": ["medium", "high"],
                "approved_defaults": {},
            }
        ),
        safety=SafetyEnforcer(policy={"enforcement_mode": "fail_closed"}),
    )


class T23SevenSystemsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = _load_inputs()
        cls.cached = _load_cached()

    def test_exactly_seven_registered_unique_ids(self) -> None:
        registry = build_default_registry()
        readiness = list_systems()

        self.assertEqual(len(SYSTEM_IDS), 7)
        self.assertEqual(len(set(SYSTEM_IDS)), 7)
        self.assertEqual(set(registry.keys()), set(SYSTEM_IDS))
        self.assertEqual(len(readiness), 7)
        self.assertEqual(get_system("always_execute").system_id, "always_execute")

    def test_common_result_schema_is_shared(self) -> None:
        system_input = self.inputs["syn_clear_execute"]
        cached = copy.deepcopy(self.cached["syn_clear_execute"])
        provider = DeterministicAnalysisProvider(
            {"syn_clear_execute": copy.deepcopy(self.cached["syn_clear_execute"])}
        )
        results = [
            AlwaysExecuteSystem().run(system_input, cached_analysis=copy.deepcopy(cached)),
            AlwaysClarifySystem().run(system_input, cached_analysis=copy.deepcopy(cached)),
            AlwaysSilentlyResolveSystem().run(system_input, cached_analysis=copy.deepcopy(cached)),
            DegreeBasedRouterSystem(
                variants_config={
                    "degree_router_thresholds": {
                        "execute_max_uncertainty": 0.15,
                        "silently_resolve_max_uncertainty": 0.4,
                    }
                }
            ).run(system_input, cached_analysis=copy.deepcopy(cached)),
            DirectBaseLLMSystem().run(system_input),
            ContextBlindManagerSystem(
                analysis_provider=provider,
                inner=_manager(provider),
            ).run(system_input),
            _manager(provider).run(system_input),
        ]

        required = {
            "record_id",
            "system_id",
            "system_version",
            "analysis",
            "recommended_strategy",
            "execution_status",
            "result_hash",
        }
        for result in results:
            self.assertTrue(required.issubset(result.to_dict().keys()))

    def test_first_three_share_analysis_fingerprint(self) -> None:
        system_input = self.inputs["syn_referential_clarify"]
        cached = copy.deepcopy(self.cached["syn_referential_clarify"])
        expected_fingerprint = cached.fingerprint()

        execute_result = AlwaysExecuteSystem().run(system_input, cached_analysis=copy.deepcopy(cached))
        clarify_result = AlwaysClarifySystem().run(system_input, cached_analysis=copy.deepcopy(cached))
        silent_result = AlwaysSilentlyResolveSystem().run(system_input, cached_analysis=copy.deepcopy(cached))

        self.assertEqual(
            execute_result.provider_provenance["shared_analysis_fingerprint"],
            expected_fingerprint,
        )
        self.assertEqual(
            clarify_result.provider_provenance["shared_analysis_fingerprint"],
            expected_fingerprint,
        )
        self.assertEqual(
            silent_result.provider_provenance["shared_analysis_fingerprint"],
            expected_fingerprint,
        )

    def test_forced_route_systems_force_their_route(self) -> None:
        system_input = self.inputs["syn_referential_clarify"]
        cached = copy.deepcopy(self.cached["syn_referential_clarify"])

        execute_result = AlwaysExecuteSystem().run(system_input, cached_analysis=copy.deepcopy(cached))
        clarify_result = AlwaysClarifySystem().run(system_input, cached_analysis=copy.deepcopy(cached))
        silent_result = AlwaysSilentlyResolveSystem().run(system_input, cached_analysis=copy.deepcopy(cached))

        self.assertEqual(execute_result.recommended_strategy, RouteLabel.EXECUTE)
        self.assertEqual(clarify_result.recommended_strategy, RouteLabel.CLARIFY)
        self.assertEqual(silent_result.recommended_strategy, RouteLabel.SILENTLY_RESOLVE)
        self.assertTrue(silent_result.runtime_metadata["resolution_attempted"])

    def test_direct_llm_is_unavailable_without_provider(self) -> None:
        result = DirectBaseLLMSystem().run(self.inputs["syn_clear_execute"])

        self.assertEqual(result.execution_status, "provider_unavailable")
        self.assertIsNone(result.recommended_strategy)

    def test_degree_router_ignores_type_and_risk_precedence(self) -> None:
        system = DegreeBasedRouterSystem(
            variants_config={
                "degree_router_thresholds": {
                    "execute_max_uncertainty": 0.15,
                    "silently_resolve_max_uncertainty": 0.4,
                }
            }
        )
        analysis = copy.deepcopy(self.cached["syn_compound_multistep"])
        analysis.risk_level = RiskLevel.HIGH
        analysis.ambiguity_present = True
        analysis.context_sampling_uncertainty = ContextSamplingUncertainty(
            score=0.0,
            variant_count=3,
            agreement=1.0,
        )

        result = system.run(self.inputs["syn_compound_multistep"], cached_analysis=analysis)

        self.assertEqual(result.recommended_strategy, RouteLabel.EXECUTE)
        self.assertFalse(result.runtime_metadata["uses_type_risk_capability_precedence"])

    def test_context_blind_manager_removes_context_without_mutating_input(self) -> None:
        record_id = "syn_spatial_silent"
        original_input = self.inputs[record_id]
        provider = DeterministicAnalysisProvider({record_id: copy.deepcopy(self.cached[record_id])})
        system = ContextBlindManagerSystem(
            analysis_provider=provider,
            inner=_manager(provider),
        )

        result = system.run(original_input)

        self.assertEqual(result.system_id, "context_blind_manager")
        self.assertTrue(result.runtime_metadata["context_ablation"]["scene_context_removed"])
        self.assertEqual(original_input.scene_context, "objects: cup; destinations: left table")
        self.assertEqual(original_input.capability_context, "capable: put")

    def test_full_manager_works_with_deterministic_provider(self) -> None:
        record_id = "syn_clear_execute"
        provider = DeterministicAnalysisProvider({record_id: copy.deepcopy(self.cached[record_id])})

        result = _manager(provider).run(self.inputs[record_id])

        self.assertEqual(result.recommended_strategy, RouteLabel.EXECUTE)
        self.assertEqual(result.provider_provenance["provider_id"], "deterministic_analysis")
        self.assertTrue(result.result_hash)


if __name__ == "__main__":
    unittest.main()
