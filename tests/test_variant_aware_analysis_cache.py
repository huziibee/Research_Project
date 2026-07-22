"""CPU-only unit tests for the variant-aware analysis cache.

Covers typed ``(record_id, analysis_variant)`` storage, per-system resolution,
integrity validation, coverage gates, legacy compatibility, and immutability.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.schema.v2.records import (  # noqa: E402
    CPC,
    CPCSlot,
    ResolvedSlotValue,
    UnresolvedSlot,
)
from ambiguity_manager.schema.v2.taxonomies import (  # noqa: E402
    AmbiguityType,
    CapabilityStatus,
    CPCSlotStatus,
    RiskLevel,
)
from ambiguity_manager.systems.analysis import (  # noqa: E402
    build_analysis_identity,
    is_context_blind_provenance,
)
from ambiguity_manager.systems.analysis_cache import (  # noqa: E402
    SHARED_FULL_CONTEXT_SYSTEMS,
    AnalysisCacheEntry,
    AnalysisCacheKey,
    AnalysisCacheStore,
    build_coverage_matrix,
    coerce_analysis_cache,
    migrate_legacy_cache,
    required_variant_for_system,
    resolve_cached_analysis_for_system,
    shared_full_context_identity_fingerprint,
)
from ambiguity_manager.systems.capabilities import load_capability_registry  # noqa: E402
from ambiguity_manager.systems.contracts import (  # noqa: E402
    AnalysisProvenance,
    StructuredAnalysis,
    SystemInput,
)
from ambiguity_manager.systems.errors import SystemsContractError  # noqa: E402
from ambiguity_manager.systems.providers import DeterministicAnalysisProvider  # noqa: E402
from ambiguity_manager.systems.variants import (  # noqa: E402
    ContextBlindManagerSystem,
    DirectBaseLLMSystem,
    SYSTEM_IDS,
)

FIXTURES_DIR = ROOT / "tests" / "fixtures" / "t16_t24_synthetic"
INPUTS_PATH = FIXTURES_DIR / "inputs.jsonl"
CACHED_ANALYSES_PATH = FIXTURES_DIR / "cached_analyses.json"


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _load_inputs() -> list[SystemInput]:
    return [SystemInput.from_dict(row) for row in _load_jsonl(INPUTS_PATH)]


def _load_cached_analyses() -> dict[str, StructuredAnalysis]:
    raw = json.loads(CACHED_ANALYSES_PATH.read_text(encoding="utf-8"))
    return {
        record_id: StructuredAnalysis.from_dict(payload)
        for record_id, payload in raw.items()
    }


def _cpc(**filled: str) -> CPC:
    c = CPC.empty_unknown()
    for key, value in filled.items():
        setattr(c, key, CPCSlot(value=value, status=CPCSlotStatus.FILLED))
    return c


def _full_context_input(record_id: str = "vac-full-1") -> SystemInput:
    return SystemInput(
        record_id=record_id,
        command="Put the cup on the table.",
        dialogue_history=("user: use the left one",),
        scene_context="objects: cup; destinations: left table",
        capability_context="capable: put",
    )


def _full_context_analysis(*, approved: bool = False) -> StructuredAnalysis:
    method = "approved" if approved else "full_context"
    return StructuredAnalysis(
        speech_act="directive_command",
        cpc=_cpc(action="put", object="cup"),
        unresolved_slots=[],
        resolved_slots=[ResolvedSlotValue(slot_name="destination", value="left table")],
        ambiguity_types=[AmbiguityType.SPATIAL],
        ambiguity_present=True,
        risk_level=RiskLevel.LOW,
        capability_status=CapabilityStatus.CAPABLE,
        analysis_provenance=AnalysisProvenance(
            provider_id="full_context_provider",
            method=method,
        ),
    )


def _context_blind_analysis(
    ablated_input: SystemInput,
    *,
    approved: bool = False,
) -> StructuredAnalysis:
    ablated_hash = ablated_input.fingerprint()
    method = "approved" if approved else "context_blind"
    return StructuredAnalysis(
        speech_act="directive_command",
        cpc=_cpc(action="put"),
        unresolved_slots=[UnresolvedSlot(slot_name="destination", reason="context_blind_no_scene")],
        resolved_slots=[],
        ambiguity_types=[AmbiguityType.SPATIAL],
        ambiguity_present=True,
        risk_level=RiskLevel.LOW,
        capability_status=CapabilityStatus.CAPABLE,
        analysis_provenance=AnalysisProvenance(
            provider_id="context_blind_cache",
            provider_version="1.0.0",
            analysis_id=ablated_hash,
            method=method,
            notes=f"ablated_input_hash={ablated_hash}",
        ),
    )


def _dual_variant_store(record: SystemInput) -> AnalysisCacheStore:
    ablated = record.without_context()
    store = AnalysisCacheStore()
    store.put(
        AnalysisCacheEntry.from_analysis(
            record=record,
            analysis=_full_context_analysis(),
            analysis_variant="full_context",
        )
    )
    store.put(
        AnalysisCacheEntry.from_analysis(
            record=record,
            analysis=_context_blind_analysis(ablated),
            analysis_variant="context_blind",
        )
    )
    return store


class AnalysisCacheKeyTests(unittest.TestCase):
    def test_analysis_cache_key_rejects_free_text_variants(self) -> None:
        with self.assertRaises(SystemsContractError):
            AnalysisCacheKey("rec-1", "custom_variant")
        with self.assertRaises(SystemsContractError):
            AnalysisCacheKey("rec-1", "FULL_CONTEXT")

    def test_one_record_stores_full_context_and_context_blind_simultaneously(self) -> None:
        record = _full_context_input()
        store = _dual_variant_store(record)
        self.assertEqual(len(store), 2)
        self.assertIn(AnalysisCacheKey(record.record_id, "full_context"), store)
        self.assertIn(AnalysisCacheKey(record.record_id, "context_blind"), store)
        self.assertIsNotNone(store.get_analysis(record.record_id, "full_context"))
        self.assertIsNotNone(store.get_analysis(record.record_id, "context_blind"))

    def test_both_variants_have_different_keys_and_source_input_hashes(self) -> None:
        record = _full_context_input()
        ablated = record.without_context()
        full_entry = AnalysisCacheEntry.from_analysis(
            record=record,
            analysis=_full_context_analysis(),
            analysis_variant="full_context",
        )
        blind_entry = AnalysisCacheEntry.from_analysis(
            record=record,
            analysis=_context_blind_analysis(ablated),
            analysis_variant="context_blind",
        )
        self.assertNotEqual(full_entry.key.as_tuple(), blind_entry.key.as_tuple())
        self.assertNotEqual(full_entry.source_input_hash, blind_entry.source_input_hash)
        self.assertEqual(full_entry.source_input_hash, record.fingerprint())
        self.assertEqual(blind_entry.source_input_hash, ablated.fingerprint())


class ResolveCachedAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = _full_context_input()
        self.store = _dual_variant_store(self.record)
        self.full_identity = shared_full_context_identity_fingerprint(
            self.store,
            self.record.record_id,
        )

    def _resolved_fingerprint(self, system_id: str) -> str | None:
        analysis = resolve_cached_analysis_for_system(
            self.store,
            record_id=self.record.record_id,
            system_id=system_id,
        )
        return None if analysis is None else analysis.fingerprint()

    def test_always_execute_receives_full_context(self) -> None:
        analysis = resolve_cached_analysis_for_system(
            self.store,
            record_id=self.record.record_id,
            system_id="always_execute",
        )
        self.assertIsNotNone(analysis)
        expected = self.store.require(self.record.record_id, "full_context").analysis
        self.assertEqual(analysis.fingerprint(), expected.fingerprint())

    def test_shared_full_context_systems_receive_identical_identity(self) -> None:
        fingerprints = {
            sid: self._resolved_fingerprint(sid) for sid in sorted(SHARED_FULL_CONTEXT_SYSTEMS)
        }
        unique = set(fingerprints.values())
        self.assertEqual(len(unique), 1, msg=fingerprints)
        self.assertIsNotNone(self.full_identity)

    def test_always_clarify_receives_exact_same_full_context_identity(self) -> None:
        execute = resolve_cached_analysis_for_system(
            self.store,
            record_id=self.record.record_id,
            system_id="always_execute",
        )
        clarify = resolve_cached_analysis_for_system(
            self.store,
            record_id=self.record.record_id,
            system_id="always_clarify",
        )
        self.assertIsNotNone(execute)
        self.assertIsNotNone(clarify)
        self.assertEqual(execute.fingerprint(), clarify.fingerprint())

    def test_always_silently_resolve_receives_exact_same_full_context_identity(self) -> None:
        execute = resolve_cached_analysis_for_system(
            self.store,
            record_id=self.record.record_id,
            system_id="always_execute",
        )
        silent = resolve_cached_analysis_for_system(
            self.store,
            record_id=self.record.record_id,
            system_id="always_silently_resolve",
        )
        self.assertIsNotNone(execute)
        self.assertIsNotNone(silent)
        self.assertEqual(execute.fingerprint(), silent.fingerprint())

    def test_degree_router_receives_full_context(self) -> None:
        self.assertEqual(
            self._resolved_fingerprint("degree_based_router"),
            self._resolved_fingerprint("always_execute"),
        )

    def test_full_manager_receives_full_context(self) -> None:
        self.assertEqual(
            self._resolved_fingerprint("full_type_risk_aware_manager"),
            self._resolved_fingerprint("always_execute"),
        )

    def test_context_blind_manager_receives_context_blind(self) -> None:
        analysis = resolve_cached_analysis_for_system(
            self.store,
            record_id=self.record.record_id,
            system_id="context_blind_manager",
        )
        self.assertIsNotNone(analysis)
        expected = self.store.require(self.record.record_id, "context_blind").analysis
        self.assertEqual(analysis.fingerprint(), expected.fingerprint())
        self.assertTrue(is_context_blind_provenance(analysis.analysis_provenance))

    def test_direct_base_llm_does_not_receive_shared_cache(self) -> None:
        analysis = resolve_cached_analysis_for_system(
            self.store,
            record_id=self.record.record_id,
            system_id="direct_base_llm",
        )
        self.assertIsNone(analysis)

    def test_missing_context_blind_does_not_fall_back_to_full_context(self) -> None:
        record = _full_context_input("vac-missing-blind")
        store = AnalysisCacheStore()
        store.put(
            AnalysisCacheEntry.from_analysis(
                record=record,
                analysis=_full_context_analysis(),
                analysis_variant="full_context",
            )
        )
        resolved = resolve_cached_analysis_for_system(
            store,
            record_id=record.record_id,
            system_id="context_blind_manager",
        )
        self.assertIsNone(resolved)
        self.assertIsNotNone(
            resolve_cached_analysis_for_system(
                store,
                record_id=record.record_id,
                system_id="always_execute",
            )
        )


class ContextBlindProviderFallbackTests(unittest.TestCase):
    def test_provider_produces_missing_context_blind_from_ablated_input(self) -> None:
        record = _full_context_input("vac-provider-blind")
        ablated = record.without_context()
        provider_analysis = StructuredAnalysis(
            speech_act="directive_command",
            cpc=_cpc(action="put"),
            unresolved_slots=[UnresolvedSlot(slot_name="destination", reason="ablated")],
            risk_level=RiskLevel.LOW,
            capability_status=CapabilityStatus.CAPABLE,
        )
        provider = DeterministicAnalysisProvider({record.record_id: provider_analysis})

        store = AnalysisCacheStore()
        store.put(
            AnalysisCacheEntry.from_analysis(
                record=record,
                analysis=_full_context_analysis(),
                analysis_variant="full_context",
            )
        )
        # Resolver must not substitute full_context for context_blind.
        self.assertIsNone(
            resolve_cached_analysis_for_system(
                store,
                record_id=record.record_id,
                system_id="context_blind_manager",
            )
        )

        system = ContextBlindManagerSystem(analysis_provider=provider)
        full_only = resolve_cached_analysis_for_system(
            store,
            record_id=record.record_id,
            system_id="always_execute",
        )
        result = system.run(record, cached_analysis=full_only)
        self.assertEqual(result.execution_status, "ok")
        self.assertNotIn("left table", str(result.analysis.to_dict()).lower())
        identity = result.runtime_metadata.get("analysis_identity") or {}
        self.assertEqual(identity.get("analysis_variant"), "context_blind")
        self.assertEqual(identity.get("source_input_hash"), ablated.fingerprint())
        self.assertNotEqual(
            identity.get("analysis_content_hash"),
            full_only.fingerprint() if full_only is not None else None,
        )


class ValidateEntryIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = _full_context_input("vac-integrity")
        self.store = AnalysisCacheStore()
        self.valid_entry = AnalysisCacheEntry.from_analysis(
            record=self.record,
            analysis=_full_context_analysis(),
            analysis_variant="full_context",
        )
        self.store.put(self.valid_entry)

    def test_wrong_variant_is_rejected(self) -> None:
        blind_analysis = _context_blind_analysis(self.record.without_context())
        bad = AnalysisCacheEntry(
            record_id=self.record.record_id,
            analysis_variant="full_context",
            source_input_hash=self.record.fingerprint(),
            analysis_content_hash=blind_analysis.fingerprint(),
            provider_id="context_blind_cache",
            provider_version="1.0.0",
            selected_base_model=None,
            selected_adapter=None,
            selected_model_strategy=None,
            prompt_contract_id=None,
            schema_version=None,
            analysis_provenance=blind_analysis.analysis_provenance.to_dict(),
            analysis=blind_analysis,
        )
        with self.assertRaises(SystemsContractError) as ctx:
            self.store.validate_entry_integrity(bad, record=self.record)
        self.assertIn("full_context cache entry has context_blind provenance", str(ctx.exception))

    def test_wrong_source_input_hash_is_rejected(self) -> None:
        bad = copy.deepcopy(self.valid_entry)
        object.__setattr__(bad, "source_input_hash", "deadbeef")
        with self.assertRaises(SystemsContractError) as ctx:
            self.store.validate_entry_integrity(bad, record=self.record)
        self.assertIn("wrong source-input hash", str(ctx.exception))

    def test_wrong_analysis_hash_is_rejected(self) -> None:
        bad = copy.deepcopy(self.valid_entry)
        object.__setattr__(bad, "analysis_content_hash", "deadbeef")
        with self.assertRaises(SystemsContractError) as ctx:
            self.store.validate_entry_integrity(bad, record=self.record)
        self.assertIn("wrong analysis content hash", str(ctx.exception))

    def test_duplicate_cache_keys_are_rejected(self) -> None:
        duplicate = AnalysisCacheEntry.from_analysis(
            record=self.record,
            analysis=_full_context_analysis(),
            analysis_variant="full_context",
        )
        with self.assertRaises(SystemsContractError) as ctx:
            self.store.put(duplicate)
        self.assertIn("duplicate analysis cache key", str(ctx.exception))


class CoverageMatrixTests(unittest.TestCase):
    def test_one_approved_cache_cannot_satisfy_all_record_coverage(self) -> None:
        record_a = _full_context_input("vac-cov-a")
        record_b = _full_context_input("vac-cov-b")
        store = _dual_variant_store(record_a)
        matrix = build_coverage_matrix(
            records=[record_a, record_b],
            systems=["always_execute", "context_blind_manager"],
            cache=store,
            run_mode="official",
        )
        self.assertFalse(matrix.all_ok())
        missing = {(row.record_id, row.system_id) for row in matrix.missing_rows()}
        self.assertIn(("vac-cov-b", "always_execute"), missing)
        self.assertIn(("vac-cov-b", "context_blind_manager"), missing)

    def test_official_coverage_requires_every_record_system_variant_combination(self) -> None:
        record = _full_context_input("vac-cov-complete-record")
        store = AnalysisCacheStore()
        store.put(
            AnalysisCacheEntry.from_analysis(
                record=record,
                analysis=_full_context_analysis(approved=True),
                analysis_variant="full_context",
            )
        )
        matrix = build_coverage_matrix(
            records=[record],
            systems=list(SYSTEM_IDS),
            cache=store,
            run_mode="official",
        )
        self.assertFalse(matrix.all_ok())
        blind_rows = [
            row
            for row in matrix.missing_rows()
            if row.system_id == "context_blind_manager"
        ]
        self.assertEqual(len(blind_rows), 1)
        self.assertEqual(blind_rows[0].validation_result, "missing_cache")
        self.assertEqual(blind_rows[0].required_analysis_variant, "context_blind")

        direct_rows = [row for row in matrix.rows if row.system_id == "direct_base_llm"]
        self.assertEqual(len(direct_rows), 1)
        self.assertEqual(direct_rows[0].validation_result, "ok")
        self.assertIsNone(direct_rows[0].required_analysis_variant)


class LegacyCacheCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = _full_context_input("vac-legacy")
        self.analysis = _full_context_analysis()

    def test_legacy_flat_cache_emits_deprecation_warning_and_maps_to_full_context(self) -> None:
        legacy = {self.record.record_id: self.analysis}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            store = coerce_analysis_cache(
                legacy,
                compatibility_mode="legacy_as_full_context",
            )
        self.assertTrue(any(issubclass(w.category, DeprecationWarning) for w in caught))
        entry = store.require(self.record.record_id, "full_context")
        self.assertEqual(entry.analysis_variant, "full_context")
        self.assertEqual(entry.analysis.fingerprint(), self.analysis.fingerprint())
        self.assertIsNone(store.get_analysis(self.record.record_id, "context_blind"))

    def test_legacy_flat_cache_rejected_in_reject_legacy_mode(self) -> None:
        legacy = {self.record.record_id: self.analysis}
        with self.assertRaises(SystemsContractError) as ctx:
            coerce_analysis_cache(legacy, compatibility_mode="reject_legacy")
        self.assertIn("legacy flat", str(ctx.exception))

    def test_migrate_legacy_cache_builds_typed_full_context_entries(self) -> None:
        legacy = {self.record.record_id: self.analysis}
        store = migrate_legacy_cache(legacy, records=[self.record])
        entry = store.require(self.record.record_id, "full_context")
        self.assertEqual(entry.source_input_hash, self.record.fingerprint())
        self.store_validate_ok(entry)

    def store_validate_ok(self, entry: AnalysisCacheEntry) -> None:
        store = AnalysisCacheStore()
        store.put(entry)
        store.validate_entry_integrity(entry, record=self.record)


class CapabilityRegistryVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_capability_registry()

    def test_required_analysis_variant_from_capability_registry(self) -> None:
        self.assertEqual(
            self.registry["always_execute"].required_analysis_variant,
            "full_context",
        )
        self.assertEqual(
            self.registry["context_blind_manager"].required_analysis_variant,
            "context_blind",
        )
        self.assertIsNone(self.registry["direct_base_llm"].required_analysis_variant)

    def test_required_variant_for_system_matches_registry(self) -> None:
        for system_id, caps in self.registry.items():
            self.assertEqual(
                required_variant_for_system(system_id),
                caps.required_analysis_variant,
            )


class DeterministicManifestTests(unittest.TestCase):
    def test_cache_manifests_are_deterministic(self) -> None:
        record_a = _full_context_input("vac-manifest-a")
        record_b = _full_context_input("vac-manifest-b")

        def build_store() -> AnalysisCacheStore:
            store = AnalysisCacheStore()
            for record in (record_b, record_a):
                store.put(
                    AnalysisCacheEntry.from_analysis(
                        record=record,
                        analysis=_full_context_analysis(),
                        analysis_variant="full_context",
                    )
                )
                ablated = record.without_context()
                store.put(
                    AnalysisCacheEntry.from_analysis(
                        record=record,
                        analysis=_context_blind_analysis(ablated),
                        analysis_variant="context_blind",
                    )
                )
            return store

        store_a = build_store()
        store_b = build_store()
        self.assertEqual(store_a.fingerprint(), store_b.fingerprint())
        self.assertEqual(store_a.to_manifest_entries(), store_b.to_manifest_entries())

        # Insertion order must not change manifest ordering.
        reversed_store = AnalysisCacheStore()
        for record in (record_a, record_b):
            reversed_store.put(
                AnalysisCacheEntry.from_analysis(
                    record=record,
                    analysis=_context_blind_analysis(record.without_context()),
                    analysis_variant="context_blind",
                )
            )
            reversed_store.put(
                AnalysisCacheEntry.from_analysis(
                    record=record,
                    analysis=_full_context_analysis(),
                    analysis_variant="full_context",
                )
            )
        self.assertEqual(store_a.fingerprint(), reversed_store.fingerprint())


class ImmutabilityTests(unittest.TestCase):
    def test_input_objects_and_cached_analyses_remain_immutable(self) -> None:
        record = _full_context_input("vac-immut")
        record_snapshot = record.to_dict()
        analysis = _full_context_analysis()
        analysis_snapshot = analysis.fingerprint()
        store = AnalysisCacheStore()
        entry = AnalysisCacheEntry.from_analysis(
            record=record,
            analysis=analysis,
            analysis_variant="full_context",
        )
        store.put(entry)

        returned = store.get_analysis(record.record_id, "full_context")
        self.assertIsNotNone(returned)
        returned.recommended_strategy = None  # type: ignore[assignment]

        self.assertEqual(record.to_dict(), record_snapshot)
        self.assertEqual(analysis.fingerprint(), analysis_snapshot)
        self.assertEqual(
            store.require(record.record_id, "full_context").analysis.fingerprint(),
            analysis_snapshot,
        )

    def test_get_analysis_returns_deep_copy(self) -> None:
        record = _full_context_input("vac-deepcopy")
        store = _dual_variant_store(record)
        first = store.get_analysis(record.record_id, "full_context")
        second = store.get_analysis(record.record_id, "full_context")
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertIsNot(first, second)
        self.assertEqual(first.fingerprint(), second.fingerprint())


class CacheSelectionOrderTests(unittest.TestCase):
    def test_result_order_does_not_change_cache_selection(self) -> None:
        record = _full_context_input("vac-order")
        store = _dual_variant_store(record)
        system_orders = [
            [
                "context_blind_manager",
                "always_execute",
                "degree_based_router",
                "full_type_risk_aware_manager",
            ],
            [
                "full_type_risk_aware_manager",
                "degree_based_router",
                "always_execute",
                "context_blind_manager",
            ],
        ]
        snapshots: list[dict[str, str | None]] = []
        for order in system_orders:
            snapshots.append(
                {
                    sid: (
                        None
                        if resolve_cached_analysis_for_system(
                            store,
                            record_id=record.record_id,
                            system_id=sid,
                        )
                        is None
                        else resolve_cached_analysis_for_system(
                            store,
                            record_id=record.record_id,
                            system_id=sid,
                        ).fingerprint()
                    )
                    for sid in order
                }
            )
        self.assertEqual(snapshots[0], snapshots[1])

    def test_runner_cache_resolution_is_independent_of_system_iteration_order(self) -> None:
        records = _load_inputs()[:1]
        record = records[0]
        cached = {record.record_id: _load_cached_analyses()[record.record_id]}
        store = migrate_legacy_cache(cached, records=records)

        class CapturingSystem:
            def __init__(self, system_id: str) -> None:
                self.system_id = system_id
                self.system_version = "capture-1.0.0"
                self.seen: list[str | None] = []

            def run(
                self,
                system_input: SystemInput,
                *,
                cached_analysis: StructuredAnalysis | None = None,
            ):
                self.seen.append(
                    None if cached_analysis is None else cached_analysis.fingerprint()
                )
                from ambiguity_manager.systems.contracts import SystemResult
                from ambiguity_manager.schema.v2.taxonomies import RouteLabel

                return SystemResult(
                    record_id=system_input.record_id,
                    system_id=self.system_id,
                    system_version=self.system_version,
                    analysis=cached_analysis or StructuredAnalysis(),
                    recommended_strategy=RouteLabel.EXECUTE,
                    execution_status="ok",
                ).with_computed_hash()

        order_a = ["always_execute", "context_blind_manager", "degree_based_router"]
        order_b = list(reversed(order_a))
        caps_a = {sid: CapturingSystem(sid) for sid in order_a}
        caps_b = {sid: CapturingSystem(sid) for sid in order_b}

        for systems, registry in ((order_a, caps_a), (order_b, caps_b)):
            for system_id in systems:
                resolved = resolve_cached_analysis_for_system(
                    store,
                    record_id=record.record_id,
                    system_id=system_id,
                )
                registry[system_id].run(record, cached_analysis=resolved)

        self.assertEqual(caps_a["always_execute"].seen, caps_b["always_execute"].seen)
        self.assertEqual(
            caps_a["context_blind_manager"].seen,
            caps_b["context_blind_manager"].seen,
        )
        self.assertEqual(
            caps_a["degree_based_router"].seen,
            caps_b["degree_based_router"].seen,
        )


class DirectBaseLLMSystemIntegrationTests(unittest.TestCase):
    def test_direct_base_llm_ignores_supplied_shared_cache_at_system_level(self) -> None:
        record = _full_context_input("vac-direct-base")
        store = _dual_variant_store(record)
        cached = resolve_cached_analysis_for_system(
            store,
            record_id=record.record_id,
            system_id="direct_base_llm",
        )
        self.assertIsNone(cached)
        system = DirectBaseLLMSystem(provider=None)
        result = system.run(record, cached_analysis=_full_context_analysis())
        self.assertEqual(result.execution_status, "provider_unavailable")
        self.assertTrue(result.runtime_metadata.get("not_executable"))


class TypedCacheCoercionTests(unittest.TestCase):
    def test_nested_variant_mapping_round_trips(self) -> None:
        record = _full_context_input("vac-nested")
        nested = {
            record.record_id: {
                "full_context": _full_context_analysis(),
                "context_blind": _context_blind_analysis(record.without_context()),
            }
        }
        store = coerce_analysis_cache(nested, compatibility_mode="reject_legacy")
        self.assertEqual(len(store), 2)
        self.assertIsNotNone(store.get_analysis(record.record_id, "full_context"))
        self.assertIsNotNone(store.get_analysis(record.record_id, "context_blind"))

    def test_string_cache_keys_with_variant_suffix(self) -> None:
        record = _full_context_input("vac-string-key")
        keyed = {
            f"{record.record_id}::full_context": _full_context_analysis(),
            f"{record.record_id}::context_blind": _context_blind_analysis(
                record.without_context()
            ),
        }
        store = coerce_analysis_cache(keyed, compatibility_mode="reject_legacy")
        self.assertEqual(len(store), 2)


class SharedIdentityFingerprintTests(unittest.TestCase):
    def test_shared_full_context_identity_matches_resolved_analysis(self) -> None:
        record = _full_context_input("vac-shared-id")
        store = _dual_variant_store(record)
        shared = shared_full_context_identity_fingerprint(store, record.record_id)
        resolved = resolve_cached_analysis_for_system(
            store,
            record_id=record.record_id,
            system_id="always_execute",
        )
        self.assertIsNotNone(shared)
        self.assertIsNotNone(resolved)
        identity = build_analysis_identity(
            record_id=record.record_id,
            source_input=record,
            analysis=resolved,
            analysis_variant="full_context",
        )
        self.assertEqual(shared, identity.fingerprint())


if __name__ == "__main__":
    unittest.main()
