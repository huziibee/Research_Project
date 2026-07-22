"""T16-T24 model identity contract and capability-registry gating tests.

Covers ``systems/capabilities.py`` (the per-system capability registry that
drives official-mode gating) and ``systems/model_identities.py`` (the model
identity contract loader/guard), plus the way ``ExperimentRunner`` combines
both to derive official-mode gates from capability *flags* rather than
hard-coded system-id string checks.

Synthetic-only. Does not select a model, adapter, or strategy, and does not
invent non-null identities: every fixture here either reuses the real,
null-selection ``configs/model/selected_identities_v1.json`` contract, or
constructs clearly-synthetic ``SelectedIdentities``/``SystemCapabilities``
objects purely to exercise the violation-detection code paths.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.systems.capabilities import (  # noqa: E402
    SystemCapabilities,
    is_provenance_approved,
    load_capability_registry,
)
from ambiguity_manager.systems.contracts import AnalysisProvenance  # noqa: E402
from ambiguity_manager.systems.errors import OfficialRunBlockedError, SystemsContractError  # noqa: E402
from ambiguity_manager.systems.execution import ExperimentRunner, OfficialPrerequisites  # noqa: E402
from ambiguity_manager.systems.model_identities import (  # noqa: E402
    SelectedIdentities,
    assert_adapter_cannot_mutate_base_identity,
    assert_adapter_matches_selected_base,
    assert_null_selection,
    assert_official_approval_state,
    assert_strategy_requires_selected_base,
    checkpoint_identity,
    load_selected_identities,
)
from ambiguity_manager.systems.variants import SYSTEM_IDS  # noqa: E402


class CapabilityRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_capability_registry()

    def test_registry_covers_all_seven_systems(self) -> None:
        self.assertEqual(set(self.registry.keys()), set(SYSTEM_IDS))

    def test_always_execute_needs_structured_analysis_but_no_model_identity(self) -> None:
        caps = self.registry["always_execute"]
        self.assertTrue(caps.requires_structured_analysis)
        self.assertTrue(caps.can_use_supplied_cached_analysis)
        self.assertFalse(caps.requires_live_model_provider)
        self.assertFalse(caps.requires_selected_base_model)
        self.assertFalse(caps.requires_selected_adapter)
        self.assertFalse(caps.requires_selected_model_strategy)
        self.assertTrue(caps.allows_full_context_cache)
        self.assertTrue(caps.requires_approved_analysis_provenance_in_official_mode)

    def test_always_clarify_and_always_silently_resolve_mirror_always_execute(self) -> None:
        always_execute = self.registry["always_execute"].to_dict()
        for sid in ("always_clarify", "always_silently_resolve"):
            other = self.registry[sid].to_dict()
            for key in always_execute:
                if key == "system_id":
                    continue
                self.assertEqual(other[key], always_execute[key], msg=f"{sid}.{key}")

    def test_direct_base_llm_is_the_only_live_provider_system(self) -> None:
        caps = self.registry["direct_base_llm"]
        self.assertFalse(caps.requires_structured_analysis)
        self.assertFalse(caps.can_use_supplied_cached_analysis)
        self.assertTrue(caps.requires_live_model_provider)
        self.assertTrue(caps.requires_selected_base_model)
        self.assertTrue(caps.forbids_selected_adapter)
        self.assertFalse(caps.allows_full_context_cache)
        for sid, caps_other in self.registry.items():
            if sid == "direct_base_llm":
                continue
            self.assertFalse(caps_other.requires_live_model_provider, msg=sid)

    def test_context_blind_and_full_manager_require_model_strategy_not_base_model(self) -> None:
        for sid in ("context_blind_manager", "full_type_risk_aware_manager"):
            caps = self.registry[sid]
            self.assertTrue(caps.requires_selected_model_strategy, msg=sid)
            self.assertFalse(caps.requires_selected_base_model, msg=sid)
            self.assertFalse(caps.requires_selected_adapter, msg=sid)
            self.assertFalse(caps.requires_live_model_provider, msg=sid)

    def test_degree_based_router_needs_neither_model_nor_strategy(self) -> None:
        caps = self.registry["degree_based_router"]
        self.assertFalse(caps.requires_selected_base_model)
        self.assertFalse(caps.requires_selected_adapter)
        self.assertFalse(caps.requires_selected_model_strategy)
        self.assertTrue(caps.allows_full_context_cache)

    def test_context_blind_manager_does_not_allow_full_context_cache(self) -> None:
        self.assertFalse(self.registry["context_blind_manager"].allows_full_context_cache)

    def test_allowed_run_modes_include_all_three_for_every_system(self) -> None:
        for sid, caps in self.registry.items():
            for mode in ("synthetic_smoke", "development", "official"):
                self.assertTrue(caps.allows_run_mode(mode), msg=f"{sid}:{mode}")

    def test_from_dict_rejects_non_object_entry(self) -> None:
        with self.assertRaises(SystemsContractError):
            SystemCapabilities.from_dict("bad_system", "not_a_dict")

    def test_from_dict_rejects_non_list_allowed_run_modes(self) -> None:
        with self.assertRaises(SystemsContractError):
            SystemCapabilities.from_dict("bad_system", {"allowed_run_modes": "official"})

    def test_from_dict_defaults_missing_bool_fields_to_false(self) -> None:
        caps = SystemCapabilities.from_dict("minimal_system", {})
        for field_name in (
            "requires_structured_analysis",
            "can_use_supplied_cached_analysis",
            "requires_live_model_provider",
            "requires_selected_base_model",
            "requires_selected_adapter",
            "requires_selected_model_strategy",
            "forbids_selected_adapter",
        ):
            self.assertFalse(getattr(caps, field_name), msg=field_name)
        self.assertTrue(caps.allows_full_context_cache)


class ProvenanceApprovalTests(unittest.TestCase):
    def test_no_provenance_is_not_approved(self) -> None:
        self.assertFalse(is_provenance_approved(None))

    def test_deterministic_method_is_not_approved(self) -> None:
        self.assertFalse(is_provenance_approved(AnalysisProvenance(method="deterministic")))

    def test_only_explicit_approved_method_is_approved(self) -> None:
        self.assertTrue(is_provenance_approved(AnalysisProvenance(method="approved")))


class SelectedIdentitiesContractTests(unittest.TestCase):
    def test_real_config_is_null_selection_and_passes_assertion(self) -> None:
        identities = assert_null_selection()
        self.assertIsNone(identities.selected_base_model)
        self.assertIsNone(identities.selected_adapter)
        self.assertIsNone(identities.selected_model_strategy)
        self.assertEqual(identities.status, "no_selection")
        self.assertFalse(identities.valid_for_official_use)

    def test_load_selected_identities_matches_assert_helper(self) -> None:
        self.assertTrue(load_selected_identities().is_null_selection())

    def test_official_prerequisites_from_selected_identities_never_invents_values(self) -> None:
        """Building prerequisites from the real identity contract must not
        invent any non-null identity; every field stays exactly what the
        contract says (null, during T16-T24)."""
        prereqs = OfficialPrerequisites.from_selected_identities()
        self.assertIsNone(prereqs.selected_base_model)
        self.assertIsNone(prereqs.selected_adapter)
        self.assertIsNone(prereqs.selected_model_strategy)

    def test_populated_base_model_fails_null_assertion(self) -> None:
        identities = SelectedIdentities(
            contract_id="selected_identities_v1",
            version="1.0.0",
            selected_base_model="org/model@deadbeef",
            selected_adapter=None,
            selected_model_strategy=None,
            status="no_selection",
            valid_for_official_use=False,
        )
        with self.assertRaises(SystemsContractError):
            identities.assert_null_selection()

    def test_valid_for_official_use_true_with_null_selection_is_rejected(self) -> None:
        identities = SelectedIdentities(
            contract_id="selected_identities_v1",
            version="1.0.0",
            selected_base_model=None,
            selected_adapter=None,
            selected_model_strategy=None,
            status="no_selection",
            valid_for_official_use=True,
        )
        with self.assertRaises(SystemsContractError):
            identities.assert_null_selection()

    def test_wrong_status_with_null_fields_is_rejected(self) -> None:
        identities = SelectedIdentities(
            contract_id="selected_identities_v1",
            version="1.0.0",
            selected_base_model=None,
            selected_adapter=None,
            selected_model_strategy=None,
            status="selected",
            valid_for_official_use=False,
        )
        with self.assertRaises(SystemsContractError):
            identities.assert_null_selection()


class ModelIdentityContractHelperTests(unittest.TestCase):
    def test_adapter_base_model_must_match_selected_base_model(self) -> None:
        base = checkpoint_identity("Qwen/Qwen3-8B", "b968826d9c46dd6066d109eabc6255188de91218")
        assert_adapter_matches_selected_base(
            selected_base_model=base,
            adapter_base_model=base,
        )
        with self.assertRaises(SystemsContractError):
            assert_adapter_matches_selected_base(
                selected_base_model=base,
                adapter_base_model=checkpoint_identity("microsoft/Phi-4", "deadbeef"),
            )

    def test_adapter_registration_cannot_mutate_base_identity(self) -> None:
        base = checkpoint_identity("Qwen/Qwen3-8B", "b968826d9c46dd6066d109eabc6255188de91218")
        assert_adapter_cannot_mutate_base_identity(
            original_selected_base_model=base,
            proposed_selected_base_model=base,
        )
        with self.assertRaises(SystemsContractError):
            assert_adapter_cannot_mutate_base_identity(
                original_selected_base_model=base,
                proposed_selected_base_model=checkpoint_identity("Qwen/Qwen3-8B", "0000000000000000000000000000000000000000"),
            )

    def test_selected_model_strategy_requires_valid_selected_base(self) -> None:
        base = checkpoint_identity("Qwen/Qwen3-8B", "b968826d9c46dd6066d109eabc6255188de91218")
        assert_strategy_requires_selected_base(selected_base_model=base)
        with self.assertRaises(SystemsContractError):
            assert_strategy_requires_selected_base(selected_base_model=None)

    def test_official_approval_remains_false_while_selection_incomplete(self) -> None:
        assert_official_approval_state(
            selected_base_model=checkpoint_identity("Qwen/Qwen3-8B", "b968826d9c46dd6066d109eabc6255188de91218"),
            selected_adapter=None,
            selected_model_strategy=None,
            status="development_base_selected",
            valid_for_official_use=False,
        )
        with self.assertRaises(SystemsContractError):
            assert_official_approval_state(
                selected_base_model=None,
                selected_adapter=None,
                selected_model_strategy=None,
                status="no_selection",
                valid_for_official_use=True,
            )


class OfficialPrerequisitesGatingTests(unittest.TestCase):
    """``OfficialPrerequisites.missing()`` derives model-identity requirements
    from capability *flags*, not from a hard-coded ``direct_base_llm`` check.
    """

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)
        self.gold_path = base / "gold.jsonl"
        self.split_path = base / "t15_split.json"
        self.gold_path.write_text("{}\n", encoding="utf-8")
        self.split_path.write_text("{}\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _base_kwargs(self) -> dict:
        return dict(
            adjudicated_gold_dataset=self.gold_path,
            t15_split_manifest=self.split_path,
            protocol_freeze_identifier="freeze-1",
            handbook_version="handbook-1",
        )

    def test_pure_cache_system_needs_no_model_identity(self) -> None:
        caps = [SystemCapabilities(system_id="always_execute")]
        prereqs = OfficialPrerequisites(**self._base_kwargs())
        self.assertEqual(prereqs.missing(capabilities=caps), [])

    def test_generic_capability_flag_not_hardcoded_to_direct_base_llm(self) -> None:
        """A made-up system_id that requires a selected base model must be
        gated the same way ``direct_base_llm`` is: the check keys off the
        capability flag, not the literal system_id string."""
        caps = [
            SystemCapabilities(
                system_id="some_future_model_backed_system",
                requires_selected_base_model=True,
            )
        ]
        prereqs = OfficialPrerequisites(**self._base_kwargs())
        self.assertIn("selected_base_model", prereqs.missing(capabilities=caps))

        satisfied = OfficialPrerequisites(**self._base_kwargs(), selected_base_model="org/model@sha")
        self.assertNotIn("selected_base_model", satisfied.missing(capabilities=caps))

    def test_requires_selected_model_strategy_flag_gates_generically(self) -> None:
        caps = [
            SystemCapabilities(
                system_id="some_strategy_dependent_system",
                requires_selected_model_strategy=True,
            )
        ]
        prereqs = OfficialPrerequisites(**self._base_kwargs())
        self.assertIn("selected_model_strategy", prereqs.missing(capabilities=caps))

        satisfied = OfficialPrerequisites(**self._base_kwargs(), selected_model_strategy="strategy-v1")
        self.assertNotIn("selected_model_strategy", satisfied.missing(capabilities=caps))

    def test_requires_selected_adapter_flag_gates_generically(self) -> None:
        caps = [SystemCapabilities(system_id="some_adapter_system", requires_selected_adapter=True)]
        prereqs = OfficialPrerequisites(**self._base_kwargs())
        self.assertIn("selected_adapter", prereqs.missing(capabilities=caps))

    def test_missing_common_prerequisites_reported_regardless_of_capabilities(self) -> None:
        prereqs = OfficialPrerequisites()
        missing = prereqs.missing(capabilities=[])
        self.assertIn("adjudicated_gold_dataset", missing)
        self.assertIn("t15_split_manifest", missing)
        self.assertIn("protocol_freeze_identifier", missing)
        self.assertIn("handbook_version", missing)

    def test_real_registry_direct_base_llm_requires_base_model_and_strategy(self) -> None:
        registry = load_capability_registry()
        caps = [registry["direct_base_llm"]]
        prereqs = OfficialPrerequisites(**self._base_kwargs())
        missing = prereqs.missing(capabilities=caps)
        self.assertIn("selected_base_model", missing)
        self.assertIn("selected_model_strategy", missing)
        self.assertNotIn("selected_adapter", missing)

    def test_real_registry_full_manager_requires_strategy_not_base_model(self) -> None:
        registry = load_capability_registry()
        caps = [registry["full_type_risk_aware_manager"]]
        prereqs = OfficialPrerequisites(**self._base_kwargs())
        missing = prereqs.missing(capabilities=caps)
        self.assertIn("selected_model_strategy", missing)
        self.assertNotIn("selected_base_model", missing)


class _StubRegisteredSystem:
    def __init__(self, provider: object | None) -> None:
        self.provider = provider


class CheckOfficialGatesRegistryDrivenTests(unittest.TestCase):
    """``ExperimentRunner.check_official_gates`` derives every check from the
    capability registry it is given, never from a hard-coded system_id."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)
        self.gold_path = base / "gold.jsonl"
        self.split_path = base / "t15_split.json"
        self.gold_path.write_text("{}\n", encoding="utf-8")
        self.split_path.write_text("{}\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _prerequisites(self, **overrides: object) -> OfficialPrerequisites:
        kwargs: dict[str, object] = dict(
            adjudicated_gold_dataset=self.gold_path,
            t15_split_manifest=self.split_path,
            protocol_freeze_identifier="freeze-1",
            handbook_version="handbook-1",
        )
        kwargs.update(overrides)
        return OfficialPrerequisites(**kwargs)

    def test_unconfigured_provider_blocks_any_capability_flagged_system(self) -> None:
        """A hypothetical, non-``direct_base_llm`` system_id that sets
        ``requires_live_model_provider`` must still be blocked when its
        provider is unconfigured: the gate is keyed off the capability flag."""
        capabilities = {
            "hypothetical_model_system": SystemCapabilities(
                system_id="hypothetical_model_system",
                requires_live_model_provider=True,
                requires_selected_base_model=True,
            )
        }
        runner = ExperimentRunner(
            registry={"hypothetical_model_system": _StubRegisteredSystem(provider=None)}
        )
        with self.assertRaises(OfficialRunBlockedError) as ctx:
            runner.check_official_gates(
                prerequisites=self._prerequisites(selected_base_model="org/model@sha"),
                systems=["hypothetical_model_system"],
                capabilities=capabilities,
                identities=load_selected_identities(),
            )
        self.assertIn("model_provider", ctx.exception.missing)

    def test_configured_provider_satisfies_live_provider_requirement(self) -> None:
        capabilities = {
            "hypothetical_model_system": SystemCapabilities(
                system_id="hypothetical_model_system",
                requires_live_model_provider=True,
                requires_selected_base_model=True,
            )
        }
        runner = ExperimentRunner(
            registry={"hypothetical_model_system": _StubRegisteredSystem(provider=object())}
        )
        # Must not raise: gold/t15/protocol/handbook/base-model are all
        # satisfied and the provider is configured.
        runner.check_official_gates(
            prerequisites=self._prerequisites(selected_base_model="org/model@sha"),
            systems=["hypothetical_model_system"],
            capabilities=capabilities,
            identities=load_selected_identities(),
        )

    def test_forbids_selected_adapter_blocks_when_adapter_selected(self) -> None:
        """``direct_base_llm`` (``forbids_selected_adapter=True`` in the real
        registry) must remain gated if the identity contract ever carried a
        non-null adapter; this is a contract violation, not a prerequisite."""
        registry = load_capability_registry()
        runner = ExperimentRunner(
            registry={"direct_base_llm": _StubRegisteredSystem(provider=object())}
        )
        hypothetically_adapted_identities = SelectedIdentities(
            contract_id="selected_identities_v1",
            version="1.0.0",
            selected_base_model="org/model@sha",
            selected_adapter="org/model-lora-v1",
            selected_model_strategy=None,
            status="selected",
            valid_for_official_use=False,
        )
        with self.assertRaises(OfficialRunBlockedError) as ctx:
            runner.check_official_gates(
                prerequisites=self._prerequisites(selected_base_model="org/model@sha"),
                systems=["direct_base_llm"],
                capabilities=registry,
                identities=hypothetically_adapted_identities,
            )
        self.assertTrue(
            any("base_model_must_remain_unadapted" in item for item in ctx.exception.missing)
        )

    def test_current_repo_state_blocks_official_run_for_every_system(self) -> None:
        """With the real, unmodified repo configs (null model identities, no
        approved-provenance mechanism yet), every system in the registry must
        still be blocked from an official run -- T16-T24 must never silently
        allow an official run to slip through. Uses the default (real)
        capability registry and identity contract, with no overrides."""
        runner = ExperimentRunner()
        for system_id in SYSTEM_IDS:
            with self.assertRaises(OfficialRunBlockedError, msg=system_id):
                runner.check_official_gates(
                    prerequisites=self._prerequisites(),
                    systems=[system_id],
                )


if __name__ == "__main__":
    unittest.main()
