"""CPU-only tests for zero-shot vs adaptation-base status separation (Phase B)."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.model.base_model_candidates import (  # noqa: E402
    load_base_model_candidate_registry,
)
from ambiguity_manager.model.base_model_selection import (  # noqa: E402
    CandidateBakeoffResult,
    apply_adaptation_base_selection,
    load_adaptation_base_selection_policy,
    validate_adaptation_base_selection_policy_payload,
)
from ambiguity_manager.paths import ProjectPaths  # noqa: E402
from ambiguity_manager.systems.capabilities import load_capability_registry  # noqa: E402
from ambiguity_manager.systems.errors import SystemsContractError  # noqa: E402
from ambiguity_manager.systems.model_identities import (  # noqa: E402
    assert_adaptation_base_selection_scope,
    assert_adapter_matches_selected_base,
    assert_direct_base_uses_no_adapter,
    assert_null_selection,
    assert_strategy_cannot_replace_base,
    assert_zero_shot_status_immutable,
    checkpoint_identity,
    load_selected_identities,
    parse_checkpoint_identity,
)

PROJECT_ROOT = ProjectPaths.from_repo_root().root
IDENTITIES_PATH = PROJECT_ROOT / "configs/model/selected_identities_v1.json"
ADAPTATION_POLICY_PATH = PROJECT_ROOT / "configs/model/adaptation_base_selection_policy_v1.json"
REGISTRY_PATH = PROJECT_ROOT / "configs/model/base_model_candidates_v1.json"


class ZeroShotAndAdaptationStatusLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.identities = load_selected_identities(IDENTITIES_PATH)
        cls.raw_identities = json.loads(IDENTITIES_PATH.read_text(encoding="utf-8"))

    def test_zero_shot_status_remains_rejected(self) -> None:
        self.assertEqual(self.identities.zero_shot_candidate_status, "rejected")
        self.assertEqual(self.raw_identities["zero_shot_candidate_status"], "rejected")

    def test_adaptation_base_status_is_separate_from_zero_shot(self) -> None:
        self.assertIsNone(self.identities.adaptation_base_status)
        self.assertEqual(self.identities.zero_shot_candidate_status, "rejected")
        self.assertNotEqual(
            self.identities.zero_shot_candidate_status,
            self.identities.adaptation_base_status,
        )

    def test_official_approval_remains_false(self) -> None:
        self.assertFalse(self.identities.valid_for_official_use)
        identities = assert_null_selection(IDENTITIES_PATH)
        self.assertFalse(identities.valid_for_official_use)

    def test_failed_zero_shot_evidence_immutable(self) -> None:
        bakeoff = self.raw_identities["bakeoff_outcome"]
        self.assertEqual(bakeoff["zero_shot_candidate_status"], "rejected")
        self.assertIn("qwen3_8b", bakeoff["candidates"])
        self.assertIn("3/4 accepted", bakeoff["candidates"]["qwen3_8b"])
        with self.assertRaises(SystemsContractError):
            assert_zero_shot_status_immutable(recorded_status="rejected", proposed_status="accepted")
        with self.assertRaises(SystemsContractError):
            assert_zero_shot_status_immutable(recorded_status="rejected", proposed_status="pending")

    def test_real_contract_null_selection_with_adaptation_pending_status(self) -> None:
        identities = assert_null_selection(IDENTITIES_PATH)
        self.assertEqual(identities.status, "adaptation_base_pending")
        self.assertIsNone(identities.selected_base_model)


class AdaptationBaseSelectionPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_adaptation_base_selection_policy(ADAPTATION_POLICY_PATH)
        cls.raw = json.loads(ADAPTATION_POLICY_PATH.read_text(encoding="utf-8"))

    def test_policy_frozen_before_application(self) -> None:
        self.assertTrue(self.policy.frozen_before_application)
        self.assertFalse(self.policy.requires_zero_shot_stage1_pass)
        self.assertFalse(self.policy.valid_for_official_use)
        self.assertTrue(self.policy.development_only)

    def test_policy_payload_validates_clean(self) -> None:
        self.assertEqual(validate_adaptation_base_selection_policy_payload(self.raw), [])

    def test_latency_must_not_override_safer_candidate_flag(self) -> None:
        self.assertTrue(self.policy.latency_must_not_override_safer_candidate)
        latency_rank = next(
            item["rank"]
            for item in self.policy.priority_criteria
            if item["criterion_id"] == "vram_and_latency"
        )
        safety_rank = next(
            item["rank"]
            for item in self.policy.priority_criteria
            if item["criterion_id"] == "severity_weighted_safety"
        )
        self.assertLess(safety_rank, latency_rank)


class AdaptationBaseSelectionApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_base_model_candidate_registry(REGISTRY_PATH)
        cls.policy = load_adaptation_base_selection_policy(ADAPTATION_POLICY_PATH)

    def _result(
        self,
        candidate_id: str,
        *,
        metrics: dict[str, float] | None = None,
        strict_structured_output_count: int = 1,
        **overrides: object,
    ) -> CandidateBakeoffResult:
        candidate = self.registry.get_candidate(candidate_id)
        kwargs: dict[str, object] = dict(
            candidate_id=candidate_id,
            checkpoint_identity=candidate.checkpoint_identity,
            stage1_passed=False,
            metrics=metrics or {},
            strict_structured_output_count=strict_structured_output_count,
        )
        kwargs.update(overrides)
        return CandidateBakeoffResult(**kwargs)  # type: ignore[arg-type]

    def test_selecting_base_does_not_select_adapter_or_strategy(self) -> None:
        metrics = {
            "structured_output_reliability": 0.9,
            "severity_weighted_safety": 0.9,
            "semantic_validity_closeness": 0.9,
            "joint_intent_cpc_quality": 0.9,
            "compound_ambiguity_quality": 0.9,
            "qlora_feasibility": 0.9,
            "context_length": 0.9,
            "runtime_stability": 0.9,
            "vram_and_latency": 1.0,
        }
        outcome = apply_adaptation_base_selection(
            {"qwen3_8b": self._result("qwen3_8b", metrics=metrics)},
            policy=self.policy,
            registry=self.registry,
        )
        self.assertIsNotNone(outcome.selected_base_model)
        self.assertIsNone(outcome.selected_adapter)
        self.assertIsNone(outcome.selected_model_strategy)
        self.assertFalse(outcome.valid_for_official_use)
        assert_adaptation_base_selection_scope(
            selected_base_model=outcome.selected_base_model,
            selected_adapter=outcome.selected_adapter,
            selected_model_strategy=outcome.selected_model_strategy,
            adaptation_base_status="selected_for_qlora_development",
            valid_for_official_use=outcome.valid_for_official_use,
        )

    def test_hard_ineligible_candidate_cannot_win(self) -> None:
        viable = self._result(
            "phi4_14b",
            metrics={
                "structured_output_reliability": 0.5,
                "severity_weighted_safety": 0.5,
                "semantic_validity_closeness": 0.5,
            },
        )
        ineligible = self._result(
            "qwen3_8b",
            strict_structured_output_count=0,
            metrics={
                "structured_output_reliability": 0.99,
                "severity_weighted_safety": 0.99,
                "semantic_validity_closeness": 0.99,
            },
        )
        outcome = apply_adaptation_base_selection(
            {"qwen3_8b": ineligible, "phi4_14b": viable},
            policy=self.policy,
            registry=self.registry,
        )
        self.assertEqual(outcome.winning_candidate_id, "phi4_14b")
        self.assertIn("qwen3_8b", outcome.rejected_candidates)
        self.assertIn("no_valid_structured_output", outcome.rejected_candidates["qwen3_8b"])

    def test_safety_severity_outranks_minor_latency_advantage(self) -> None:
        shared = {
            "structured_output_reliability": 0.85,
            "semantic_validity_closeness": 0.8,
            "joint_intent_cpc_quality": 0.7,
            "compound_ambiguity_quality": 0.7,
            "qlora_feasibility": 0.9,
            "context_length": 0.9,
            "runtime_stability": 0.9,
        }
        fast_less_safe = self._result(
            "qwen3_8b",
            metrics={**shared, "severity_weighted_safety": 0.3, "vram_and_latency": 0.1},
        )
        slow_safer = self._result(
            "phi4_14b",
            metrics={**shared, "severity_weighted_safety": 0.95, "vram_and_latency": 0.9},
        )
        outcome = apply_adaptation_base_selection(
            {"qwen3_8b": fast_less_safe, "phi4_14b": slow_safer},
            policy=self.policy,
            registry=self.registry,
        )
        self.assertEqual(outcome.winning_candidate_id, "phi4_14b")

    def test_no_viable_base_leaves_selected_base_model_null(self) -> None:
        outcome = apply_adaptation_base_selection(
            {
                "qwen3_8b": self._result("qwen3_8b", strict_structured_output_count=0),
                "phi4_14b": self._result("phi4_14b", qlora_feasible=False),
                "mistral_small_24b_2501": self._result(
                    "mistral_small_24b_2501",
                    runtime_compatible=False,
                ),
            },
            policy=self.policy,
            registry=self.registry,
        )
        self.assertIsNone(outcome.selected_base_model)
        self.assertEqual(outcome.status, "no_viable_adaptation_base")

    def test_adaptation_path_does_not_require_zero_shot_stage1_pass(self) -> None:
        outcome = apply_adaptation_base_selection(
            {
                "qwen3_8b": self._result(
                    "qwen3_8b",
                    stage1_passed=False,
                    metrics={
                        "structured_output_reliability": 0.75,
                        "severity_weighted_safety": 0.8,
                        "semantic_validity_closeness": 0.7,
                        "joint_intent_cpc_quality": 0.7,
                        "compound_ambiguity_quality": 0.7,
                        "qlora_feasibility": 0.9,
                        "context_length": 0.9,
                        "runtime_stability": 0.9,
                        "vram_and_latency": 1.0,
                    },
                )
            },
            policy=self.policy,
            registry=self.registry,
        )
        self.assertIsNotNone(outcome.selected_base_model)
        self.assertFalse(outcome.valid_for_official_use)


class ModelIdentityImmutabilityTests(unittest.TestCase):
    def test_base_identity_exact_and_immutable(self) -> None:
        identity = checkpoint_identity("Qwen/Qwen3-8B", "b968826d9c46dd6066d109eabc6255188de91218")
        repository, revision = parse_checkpoint_identity(identity)
        self.assertEqual(repository, "Qwen/Qwen3-8B")
        self.assertEqual(revision, "b968826d9c46dd6066d109eabc6255188de91218")
        self.assertEqual(
            identity,
            checkpoint_identity("Qwen/Qwen3-8B", "b968826d9c46dd6066d109eabc6255188de91218"),
        )

    def test_adapter_must_reference_exact_base(self) -> None:
        base = checkpoint_identity("Qwen/Qwen3-8B", "b968826d9c46dd6066d109eabc6255188de91218")
        assert_adapter_matches_selected_base(selected_base_model=base, adapter_base_model=base)
        with self.assertRaises(SystemsContractError):
            assert_adapter_matches_selected_base(
                selected_base_model=base,
                adapter_base_model=checkpoint_identity("microsoft/Phi-4", "deadbeef"),
            )

    def test_direct_base_baseline_uses_no_adapter(self) -> None:
        registry = load_capability_registry()
        caps = registry["direct_base_llm"]
        self.assertTrue(caps.forbids_selected_adapter)
        base = checkpoint_identity("Qwen/Qwen3-8B", "b968826d9c46dd6066d109eabc6255188de91218")
        assert_direct_base_uses_no_adapter(
            selected_base_model=base,
            selected_adapter=None,
            forbids_selected_adapter=True,
        )
        with self.assertRaises(SystemsContractError):
            assert_direct_base_uses_no_adapter(
                selected_base_model=base,
                selected_adapter="qwen3-lora-smoke",
                forbids_selected_adapter=True,
            )

    def test_strategy_cannot_silently_replace_base(self) -> None:
        base = checkpoint_identity("Qwen/Qwen3-8B", "b968826d9c46dd6066d109eabc6255188de91218")
        assert_strategy_cannot_replace_base(
            original_selected_base_model=base,
            proposed_selected_base_model=base,
            selected_model_strategy="manager-strategy-v1",
        )
        with self.assertRaises(SystemsContractError):
            assert_strategy_cannot_replace_base(
                original_selected_base_model=base,
                proposed_selected_base_model=checkpoint_identity("microsoft/Phi-4", "deadbeef"),
                selected_model_strategy="manager-strategy-v1",
            )


class BackwardCompatibilityTests(unittest.TestCase):
    def test_legacy_config_without_status_layers_infers_zero_shot_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy_identities.json"
            payload = copy.deepcopy(json.loads(IDENTITIES_PATH.read_text(encoding="utf-8")))
            payload.pop("zero_shot_candidate_status", None)
            payload.pop("adaptation_base_status", None)
            payload["status"] = "no_viable_base_candidate"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            identities = load_selected_identities(path)
            self.assertEqual(identities.zero_shot_candidate_status, "rejected")


if __name__ == "__main__":
    unittest.main()
