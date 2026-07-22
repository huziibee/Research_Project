"""T16-T24 model identity contract and capability-registry-driven gate tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.paths import ProjectPaths  # noqa: E402
from ambiguity_manager.systems.capabilities import (  # noqa: E402
    SystemCapabilities,
    is_provenance_approved,
    load_capability_registry,
)
from ambiguity_manager.systems.contracts import AnalysisProvenance, StructuredAnalysis, SystemInput  # noqa: E402
from ambiguity_manager.systems.errors import OfficialRunBlockedError, SystemsContractError  # noqa: E402
from ambiguity_manager.systems.execution import ExperimentRunner, OfficialPrerequisites  # noqa: E402
from ambiguity_manager.systems.model_identities import (  # noqa: E402
    IDENTITY_FIELDS,
    SelectedIdentities,
    assert_null_selection,
    load_selected_identities,
)
from ambiguity_manager.systems.variants import SYSTEM_IDS  # noqa: E402

IDENTITIES_PATH = (
    ProjectPaths.from_repo_root().configs / "model" / "selected_identities_v1.json"
)
LICENCE_REGISTER_PATH = (
    ProjectPaths.from_repo_root().configs / "licences" / "model_licence_register.json"
)


class StubProviderSystem:
    def __init__(self, system_id: str, *, provider: object | None) -> None:
        self.system_id = system_id
        self.system_version = "1.0.0"
        self.provider = provider

    def run(self, system_input, *, cached_analysis=None):  # pragma: no cover - not exercised
        raise NotImplementedError


class ModelIdentityContractTests(unittest.TestCase):
    def test_contract_file_has_all_null_identities(self) -> None:
        raw = json.loads(IDENTITIES_PATH.read_text(encoding="utf-8"))
        self.assertIsNone(raw["selected_base_model"])
        self.assertIsNone(raw["selected_adapter"])
        self.assertIsNone(raw["selected_model_strategy"])
        self.assertEqual(raw["status"], "no_selection")
        self.assertFalse(raw["valid_for_official_use"])

    def test_contract_file_documents_legacy_field_deprecation(self) -> None:
        raw = json.loads(IDENTITIES_PATH.read_text(encoding="utf-8"))
        legacy = raw["legacy_selected_model_field"]
        self.assertEqual(legacy["path"], "configs/licences/model_licence_register.json")
        self.assertEqual(legacy["field"], "selected_model")
        self.assertEqual(legacy["status"], "deprecated_use_selected_identities_v1")

    def test_load_selected_identities_returns_null_selection(self) -> None:
        identities = load_selected_identities()
        self.assertIsInstance(identities, SelectedIdentities)
        for field in IDENTITY_FIELDS:
            self.assertIsNone(getattr(identities, field))
        self.assertTrue(identities.is_null_selection())
        self.assertFalse(identities.valid_for_official_use)

    def test_assert_null_selection_passes_for_current_contract(self) -> None:
        identities = assert_null_selection()
        self.assertTrue(identities.is_null_selection())

    def test_assert_null_selection_raises_if_a_field_is_populated(self) -> None:
        populated = SelectedIdentities(
            contract_id="selected_identities_v1",
            version="1.0.0",
            selected_base_model="org/model@deadbeef",
            selected_adapter=None,
            selected_model_strategy=None,
            status="no_selection",
            valid_for_official_use=False,
        )
        with self.assertRaises(SystemsContractError):
            populated.assert_null_selection()

    def test_assert_null_selection_raises_if_status_is_not_no_selection(self) -> None:
        mismatched_status = SelectedIdentities(
            contract_id="selected_identities_v1",
            version="1.0.0",
            selected_base_model=None,
            selected_adapter=None,
            selected_model_strategy=None,
            status="selected",
            valid_for_official_use=False,
        )
        with self.assertRaises(SystemsContractError):
            mismatched_status.assert_null_selection()

    def test_assert_null_selection_raises_if_valid_for_official_use_true(self) -> None:
        contradictory = SelectedIdentities(
            contract_id="selected_identities_v1",
            version="1.0.0",
            selected_base_model=None,
            selected_adapter=None,
            selected_model_strategy=None,
            status="no_selection",
            valid_for_official_use=True,
        )
        with self.assertRaises(SystemsContractError):
            contradictory.assert_null_selection()

    def test_licence_register_selected_model_remains_null_and_documents_deprecation(self) -> None:
        raw = json.loads(LICENCE_REGISTER_PATH.read_text(encoding="utf-8"))
        self.assertIsNone(raw["selected_model"])
        self.assertEqual(
            raw["deprecated"]["selected_model"]["status"],
            "deprecated_use_selected_identities_v1",
        )
        self.assertEqual(
            raw["deprecated"]["selected_model"]["superseded_by"],
            "configs/model/selected_identities_v1.json",
        )

    def test_official_prerequisites_load_null_identities_from_contract(self) -> None:
        prerequisites = OfficialPrerequisites.from_selected_identities()
        self.assertIsNone(prerequisites.selected_base_model)
        self.assertIsNone(prerequisites.selected_adapter)
        self.assertIsNone(prerequisites.selected_model_strategy)


class CapabilityRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_capability_registry()

    def test_registry_has_entry_for_every_system(self) -> None:
        self.assertEqual(set(self.registry.keys()), set(SYSTEM_IDS))
        for cap in self.registry.values():
            self.assertIsInstance(cap, SystemCapabilities)

    def test_always_x_systems_can_use_cache_but_not_live_provider(self) -> None:
        for sid in ("always_execute", "always_clarify", "always_silently_resolve"):
            cap = self.registry[sid]
            self.assertTrue(cap.can_use_supplied_cached_analysis)
            self.assertFalse(cap.requires_live_model_provider)
            self.assertTrue(cap.requires_approved_analysis_provenance_in_official_mode)
            self.assertFalse(cap.requires_selected_base_model)
            self.assertFalse(cap.requires_selected_adapter)

    def test_direct_base_llm_requires_base_model_and_forbids_adapter(self) -> None:
        cap = self.registry["direct_base_llm"]
        self.assertTrue(cap.requires_live_model_provider)
        self.assertTrue(cap.requires_selected_base_model)
        self.assertTrue(cap.forbids_selected_adapter)
        self.assertFalse(cap.can_use_supplied_cached_analysis)

    def test_degree_based_router_may_use_approved_cache_deterministically(self) -> None:
        cap = self.registry["degree_based_router"]
        self.assertTrue(cap.can_use_supplied_cached_analysis)
        self.assertFalse(cap.requires_live_model_provider)

    def test_context_blind_manager_cannot_use_full_context_cache(self) -> None:
        cap = self.registry["context_blind_manager"]
        self.assertFalse(cap.allows_full_context_cache)
        self.assertTrue(cap.requires_selected_model_strategy)

    def test_full_type_risk_aware_manager_requires_selected_model_strategy(self) -> None:
        cap = self.registry["full_type_risk_aware_manager"]
        self.assertTrue(cap.requires_selected_model_strategy)
        self.assertTrue(cap.allows_full_context_cache)

    def test_all_systems_currently_allow_all_three_run_modes(self) -> None:
        for cap in self.registry.values():
            self.assertTrue(cap.allows_run_mode("synthetic_smoke"))
            self.assertTrue(cap.allows_run_mode("development"))
            self.assertTrue(cap.allows_run_mode("official"))

    def test_round_trip_to_dict_from_dict(self) -> None:
        cap = self.registry["context_blind_manager"]
        rebuilt = SystemCapabilities.from_dict(cap.system_id, cap.to_dict())
        self.assertEqual(rebuilt, cap)

    def test_is_provenance_approved_defaults_to_false(self) -> None:
        self.assertFalse(is_provenance_approved(AnalysisProvenance()))
        self.assertFalse(is_provenance_approved(AnalysisProvenance(method="deterministic")))

    def test_is_provenance_approved_true_only_when_explicitly_tagged(self) -> None:
        self.assertTrue(is_provenance_approved(AnalysisProvenance(method="approved")))


class OfficialGateDerivationTests(unittest.TestCase):
    """Gates must come from the capability registry, not system-id checks."""

    def _prerequisites(self, tmp_path: Path) -> OfficialPrerequisites:
        gold = tmp_path / "gold.jsonl"
        split = tmp_path / "split.json"
        gold.write_text("{}\n", encoding="utf-8")
        split.write_text("{}\n", encoding="utf-8")
        return OfficialPrerequisites(
            adjudicated_gold_dataset=gold,
            t15_split_manifest=split,
            protocol_freeze_identifier="freeze-1",
            handbook_version="handbook-1",
        )

    def test_non_model_backed_system_without_provider_is_not_flagged_for_model_provider(self) -> None:
        runner = ExperimentRunner(registry={"always_execute": StubProviderSystem("always_execute", provider=None)})
        with tempfile.TemporaryDirectory() as tmpdir:
            prerequisites = self._prerequisites(Path(tmpdir))
            with self.assertRaises(OfficialRunBlockedError) as ctx:
                runner.check_official_gates(
                    prerequisites=prerequisites,
                    systems=["always_execute"],
                )
        # always_execute does not require a live provider, so the fact that
        # this stub has provider=None must not trigger a model_provider
        # complaint (that requirement is registry-derived, not name-derived).
        self.assertNotIn("model_provider", ctx.exception.missing)

    def test_arbitrary_system_declared_live_provider_dependent_is_gated_generically(self) -> None:
        """A hypothetical new system flagged as live-provider-dependent in the
        registry must be gated the same way direct_base_llm is, proving the
        gate is not hard-coded to that one system id."""
        capabilities = load_capability_registry()
        synthetic_capabilities = dict(capabilities)
        synthetic_capabilities["always_execute"] = SystemCapabilities(
            system_id="always_execute",
            requires_live_model_provider=True,
        )
        runner = ExperimentRunner(registry={"always_execute": StubProviderSystem("always_execute", provider=None)})
        with tempfile.TemporaryDirectory() as tmpdir:
            prerequisites = self._prerequisites(Path(tmpdir))
            with self.assertRaises(OfficialRunBlockedError) as ctx:
                runner.check_official_gates(
                    prerequisites=prerequisites,
                    systems=["always_execute"],
                    capabilities=synthetic_capabilities,
                )
        self.assertIn("model_provider", ctx.exception.missing)

    def test_direct_base_llm_missing_selected_base_model_is_blocked(self) -> None:
        runner = ExperimentRunner(
            registry={"direct_base_llm": StubProviderSystem("direct_base_llm", provider=object())}
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            prerequisites = self._prerequisites(Path(tmpdir))
            with self.assertRaises(OfficialRunBlockedError) as ctx:
                runner.check_official_gates(
                    prerequisites=prerequisites,
                    systems=["direct_base_llm"],
                )
        self.assertIn("selected_base_model", ctx.exception.missing)

    def test_direct_base_llm_with_adapter_selected_is_blocked_as_unadapted_base_violation(self) -> None:
        runner = ExperimentRunner(
            registry={"direct_base_llm": StubProviderSystem("direct_base_llm", provider=object())}
        )
        identities = SelectedIdentities(
            contract_id="selected_identities_v1",
            version="1.0.0",
            selected_base_model="org/model@deadbeef",
            selected_adapter="org/adapter@cafef00d",
            selected_model_strategy=None,
            status="selected",
            valid_for_official_use=True,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            prerequisites = self._prerequisites(Path(tmpdir))
            prerequisites.selected_base_model = identities.selected_base_model
            with self.assertRaises(OfficialRunBlockedError) as ctx:
                runner.check_official_gates(
                    prerequisites=prerequisites,
                    systems=["direct_base_llm"],
                    identities=identities,
                )
        self.assertIn("direct_base_llm:base_model_must_remain_unadapted", ctx.exception.missing)

    def test_context_blind_manager_requires_selected_model_strategy_for_official(self) -> None:
        runner = ExperimentRunner(registry={"context_blind_manager": StubProviderSystem("context_blind_manager", provider=None)})
        with tempfile.TemporaryDirectory() as tmpdir:
            prerequisites = self._prerequisites(Path(tmpdir))
            with self.assertRaises(OfficialRunBlockedError) as ctx:
                runner.check_official_gates(
                    prerequisites=prerequisites,
                    systems=["context_blind_manager"],
                )
        self.assertIn("selected_model_strategy", ctx.exception.missing)

    def test_cache_backed_systems_blocked_without_approved_provenance(self) -> None:
        runner = ExperimentRunner(registry={"always_execute": StubProviderSystem("always_execute", provider=None)})
        unapproved = StructuredAnalysis(analysis_provenance=AnalysisProvenance(method="deterministic"))
        with tempfile.TemporaryDirectory() as tmpdir:
            prerequisites = self._prerequisites(Path(tmpdir))
            prerequisites.selected_model_strategy = "strategy-1"
            with self.assertRaises(OfficialRunBlockedError) as ctx:
                runner.check_official_gates(
                    prerequisites=prerequisites,
                    systems=["always_execute"],
                    cached_analyses={"rec-1": unapproved},
                )
        self.assertIn("always_execute:approved_analysis_provenance", ctx.exception.missing)

    def test_cache_backed_systems_pass_provenance_check_when_approved(self) -> None:
        runner = ExperimentRunner(registry={"always_execute": StubProviderSystem("always_execute", provider=None)})
        approved = StructuredAnalysis(analysis_provenance=AnalysisProvenance(method="approved"))
        with tempfile.TemporaryDirectory() as tmpdir:
            prerequisites = self._prerequisites(Path(tmpdir))
            try:
                runner.check_official_gates(
                    prerequisites=prerequisites,
                    systems=["always_execute"],
                    cached_analyses={"rec-1": approved},
                )
            except OfficialRunBlockedError as exc:
                self.assertNotIn("always_execute:approved_analysis_provenance", exc.missing)
            else:
                pass


class OfficialPrerequisitesTests(unittest.TestCase):
    def test_missing_reports_nothing_extra_when_no_systems_need_identities(self) -> None:
        prerequisites = OfficialPrerequisites(
            adjudicated_gold_dataset=Path(__file__),
            t15_split_manifest=Path(__file__),
            protocol_freeze_identifier="freeze-1",
            handbook_version="handbook-1",
        )
        cap = SystemCapabilities(system_id="always_execute")
        missing = prerequisites.missing(capabilities=[cap])
        self.assertNotIn("selected_base_model", missing)
        self.assertNotIn("selected_adapter", missing)
        self.assertNotIn("selected_model_strategy", missing)

    def test_missing_reports_identity_fields_only_when_required_by_a_system(self) -> None:
        prerequisites = OfficialPrerequisites(
            adjudicated_gold_dataset=Path(__file__),
            t15_split_manifest=Path(__file__),
            protocol_freeze_identifier="freeze-1",
            handbook_version="handbook-1",
        )
        caps = [
            SystemCapabilities(system_id="direct_base_llm", requires_selected_base_model=True),
        ]
        missing = prerequisites.missing(capabilities=caps)
        self.assertIn("selected_base_model", missing)


if __name__ == "__main__":
    unittest.main()
