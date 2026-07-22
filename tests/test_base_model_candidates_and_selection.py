"""CPU-only tests for base-model candidate registry and selection policy."""

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
    ALLOWLISTED_CANDIDATE_IDS,
    BaseModelRegistryError,
    get_candidate_by_id,
    load_base_model_candidate_registry,
    registry_canonical_hash,
    validate_registry_payload,
)
from ambiguity_manager.model.base_model_selection import (  # noqa: E402
    BaseModelSelectionError,
    CandidateBakeoffResult,
    apply_selection,
    load_base_model_selection_policy,
    validate_selection_policy_payload,
)
from ambiguity_manager.paths import ProjectPaths  # noqa: E402
from ambiguity_manager.systems.model_identities import (  # noqa: E402
    assert_null_selection,
    checkpoint_identity,
    load_selected_identities,
)

PROJECT_ROOT = ProjectPaths.from_repo_root().root
REGISTRY_PATH = PROJECT_ROOT / "configs/model/base_model_candidates_v1.json"
POLICY_PATH = PROJECT_ROOT / "configs/model/base_model_selection_policy_v1.json"
IDENTITIES_PATH = PROJECT_ROOT / "configs/model/selected_identities_v1.json"


class BaseModelCandidateRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_base_model_candidate_registry(REGISTRY_PATH)
        cls.raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_exactly_three_allowlisted_candidates(self) -> None:
        self.assertEqual(len(self.registry.candidates), 3)
        self.assertEqual(self.registry.candidate_ids, ALLOWLISTED_CANDIDATE_IDS)

    def test_exact_revisions_required(self) -> None:
        expected = {
            "qwen3_8b": "b968826d9c46dd6066d109eabc6255188de91218",
            "phi4_14b": "2db69c1c3e91a05d2c64a3185acfbaf36f744e25",
            "mistral_small_24b_2501": "9527884be6e5616bdd54de542f9ae13384489724",
        }
        for candidate_id, revision in expected.items():
            candidate = self.registry.get_candidate(candidate_id)
            self.assertEqual(candidate.revision, revision)
            self.assertEqual(candidate.tokenizer_revision, revision)

    def test_licence_evidence_required(self) -> None:
        for candidate in self.registry.candidates:
            self.assertTrue(candidate.licence_evidence_url.startswith("https://huggingface.co/"))
            self.assertGreaterEqual(len(candidate.official_source_references), 2)

    def test_gated_private_candidates_rejected_unless_authorised(self) -> None:
        for candidate in self.registry.candidates:
            self.assertFalse(candidate.gated)
            self.assertFalse(candidate.private)
            self.assertFalse(candidate.gated_access_authorised)

        mutated = copy.deepcopy(self.raw)
        mutated["candidates"][1]["gated"] = True
        mutated["candidates"][1]["gated_access_authorised"] = False
        errors = validate_registry_payload(mutated, verify_hash=False)
        self.assertTrue(any("gated/private candidate rejected" in item for item in errors))

    def test_model_ids_allowlisted(self) -> None:
        with self.assertRaises(BaseModelRegistryError):
            get_candidate_by_id("not_allowlisted", registry=self.registry)

    def test_selected_base_model_initially_null(self) -> None:
        self.assertIsNone(self.registry.selected_base_model)
        self.registry.assert_null_selection()

    def test_adapter_and_strategy_initially_null(self) -> None:
        self.assertIsNone(self.registry.selected_adapter)
        self.assertIsNone(self.registry.selected_model_strategy)

    def test_canonical_hash_matches_body(self) -> None:
        self.assertEqual(self.registry.canonical_hash, registry_canonical_hash(self.raw))
        self.assertEqual(
            self.registry.canonical_hash,
            "d7bd41c1f841afd197a9521bdca0a3fc89ee4b9c0803e41bbd0cf7953dcc4934",
        )

    def test_development_only_and_not_official(self) -> None:
        self.assertTrue(self.registry.development_only)
        self.assertFalse(self.registry.valid_for_official_use)
        self.assertEqual(self.registry.status, "development_shortlist")

    def test_stage1_thresholds_frozen(self) -> None:
        thresholds = self.registry.development_bakeoff_thresholds
        self.assertEqual(thresholds["transport_accepted_records_min"], 4)
        self.assertEqual(thresholds["transport_records_required"], 4)
        self.assertEqual(thresholds["max_invalid_final_schema"], 0)
        self.assertEqual(thresholds["max_unrecorded_attempts"], 0)
        self.assertEqual(thresholds["max_unsupported_commitments_on_accepted"], 0)
        self.assertEqual(thresholds["max_unsafe_silent_commitments"], 0)
        self.assertFalse(thresholds["unconstrained_fallback_permitted"])

    def test_pinned_runtime_identity(self) -> None:
        runtime = self.registry.official_source_references["pinned_runtime"]
        self.assertEqual(runtime["container_filename"], "vllm-openai-v0.20.1.sif")
        self.assertEqual(
            runtime["container_sha256"],
            "d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1",
        )

    def test_get_candidate_by_id_helper(self) -> None:
        candidate = get_candidate_by_id("qwen3_8b", registry=self.registry)
        self.assertEqual(
            candidate.checkpoint_identity,
            checkpoint_identity("Qwen/Qwen3-8B", "b968826d9c46dd6066d109eabc6255188de91218"),
        )

    def test_screened_out_records_rejection_reasons(self) -> None:
        self.assertGreaterEqual(len(self.registry.screened_out), 3)
        for entry in self.registry.screened_out:
            self.assertTrue(entry["rejection_reason"])


class BaseModelSelectionPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_base_model_selection_policy(POLICY_PATH)
        cls.raw = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    def test_policy_frozen_before_stage_2(self) -> None:
        self.assertEqual(self.policy.status, "frozen_for_development_bakeoff")
        self.assertTrue(self.policy.frozen_before_stage_2)
        self.assertFalse(self.policy.valid_for_official_use)

    def test_priority_order_matches_section_18(self) -> None:
        criterion_ids = [item["criterion_id"] for item in self.policy.priority_criteria]
        self.assertEqual(
            criterion_ids,
            [
                "safety_and_unsupported_commitments",
                "structured_output_reliability",
                "joint_intent_cpc_quality",
                "compound_ambiguity_quality",
                "context_use_and_blind_separation",
                "qlora_feasibility",
                "operational_cost_and_latency",
            ],
        )

    def test_weights_frozen_without_tune_after_results_notes(self) -> None:
        for item in self.policy.priority_criteria:
            self.assertNotIn("tune after", item["description"].lower())
        errors = validate_selection_policy_payload(self.raw)
        self.assertEqual(errors, [])

    def test_selected_base_model_remains_null_in_policy(self) -> None:
        self.assertIsNone(self.policy.selected_base_model)
        self.assertIsNone(self.policy.selected_adapter)
        self.assertIsNone(self.policy.selected_model_strategy)


class BaseModelSelectionApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_base_model_candidate_registry(REGISTRY_PATH)
        cls.policy = load_base_model_selection_policy(POLICY_PATH)

    def _result(
        self,
        candidate_id: str,
        *,
        metrics: dict[str, float] | None = None,
        stage1_passed: bool = True,
        hard_gate_failures: tuple[str, ...] = (),
        unsafe_silent_commitments: int = 0,
        unsupported_commitments_on_accepted: int = 0,
        **overrides: object,
    ) -> CandidateBakeoffResult:
        candidate = self.registry.get_candidate(candidate_id)
        kwargs: dict[str, object] = dict(
            candidate_id=candidate_id,
            checkpoint_identity=candidate.checkpoint_identity,
            stage1_passed=stage1_passed,
            hard_gate_failures=hard_gate_failures,
            metrics=metrics or {},
            unsafe_silent_commitments=unsafe_silent_commitments,
            unsupported_commitments_on_accepted=unsupported_commitments_on_accepted,
        )
        kwargs.update(overrides)
        return CandidateBakeoffResult(**kwargs)  # type: ignore[arg-type]

    def test_hard_gate_failure_rejects_candidate(self) -> None:
        outcome = apply_selection(
            {
                "qwen3_8b": self._result("qwen3_8b", stage1_passed=False),
            },
            policy=self.policy,
            registry=self.registry,
        )
        self.assertIsNone(outcome.selected_base_model)
        self.assertEqual(outcome.status, "no_viable_base_candidate")
        self.assertIn("qwen3_8b", outcome.rejected_candidates)

    def test_unsafe_candidate_cannot_win_on_semantic_score(self) -> None:
        unsafe = self._result(
            "qwen3_8b",
            metrics={
                "safety_and_unsupported_commitments": 0.1,
                "structured_output_reliability": 0.99,
                "joint_intent_cpc_quality": 0.99,
            },
            unsafe_silent_commitments=1,
        )
        safe = self._result(
            "phi4_14b",
            metrics={
                "safety_and_unsupported_commitments": 0.8,
                "structured_output_reliability": 0.7,
                "joint_intent_cpc_quality": 0.6,
            },
        )
        outcome = apply_selection(
            {"qwen3_8b": unsafe, "phi4_14b": safe},
            policy=self.policy,
            registry=self.registry,
        )
        self.assertEqual(outcome.winning_candidate_id, "phi4_14b")

    def test_exact_tie_break_uses_candidate_id_lexicographic(self) -> None:
        metrics = {
            "safety_and_unsupported_commitments": 0.9,
            "structured_output_reliability": 0.9,
            "joint_intent_cpc_quality": 0.9,
            "compound_ambiguity_quality": 0.9,
            "context_use_and_blind_separation": 0.9,
            "qlora_feasibility": 0.9,
            "operational_cost_and_latency": 1.0,
        }
        outcome = apply_selection(
            {
                "mistral_small_24b_2501": self._result("mistral_small_24b_2501", metrics=metrics),
                "phi4_14b": self._result("phi4_14b", metrics=metrics),
            },
            policy=self.policy,
            registry=self.registry,
        )
        self.assertTrue(outcome.tie_break_applied)
        self.assertEqual(outcome.winning_candidate_id, "mistral_small_24b_2501")

    def test_no_viable_candidate_leaves_null_selection(self) -> None:
        outcome = apply_selection(
            {
                "qwen3_8b": self._result("qwen3_8b", stage1_passed=False),
                "phi4_14b": self._result("phi4_14b", hard_gate_failures=("runtime_incompatibility",)),
                "mistral_small_24b_2501": self._result(
                    "mistral_small_24b_2501",
                    qlora_feasible=False,
                ),
            },
            policy=self.policy,
            registry=self.registry,
        )
        self.assertIsNone(outcome.selected_base_model)
        self.assertIsNone(outcome.selected_adapter)
        self.assertIsNone(outcome.selected_model_strategy)
        self.assertFalse(outcome.valid_for_official_use)

    def test_winner_returns_identity_dict_without_writing_contract(self) -> None:
        outcome = apply_selection(
            {
                "qwen3_8b": self._result(
                    "qwen3_8b",
                    metrics={
                        "safety_and_unsupported_commitments": 0.95,
                        "structured_output_reliability": 0.95,
                        "joint_intent_cpc_quality": 0.95,
                        "compound_ambiguity_quality": 0.95,
                        "context_use_and_blind_separation": 0.95,
                        "qlora_feasibility": 0.95,
                        "operational_cost_and_latency": 1.0,
                    },
                )
            },
            policy=self.policy,
            registry=self.registry,
        )
        identity_update = outcome.identity_update()
        self.assertEqual(
            identity_update["selected_base_model"],
            checkpoint_identity("Qwen/Qwen3-8B", "b968826d9c46dd6066d109eabc6255188de91218"),
        )
        self.assertIsNone(identity_update["selected_adapter"])
        self.assertIsNone(identity_update["selected_model_strategy"])
        self.assertFalse(identity_update["valid_for_official_use"])

        identities = load_selected_identities(IDENTITIES_PATH)
        self.assertIsNone(identities.selected_base_model)

    def test_non_allowlisted_result_ids_rejected(self) -> None:
        with self.assertRaises(BaseModelSelectionError):
            apply_selection(
                {
                    "unknown": CandidateBakeoffResult(
                        candidate_id="unknown",
                        checkpoint_identity="org/model@deadbeef",
                        stage1_passed=True,
                    )
                },
                policy=self.policy,
                registry=self.registry,
            )


class SelectedIdentitiesContractIntegrationTests(unittest.TestCase):
    def test_real_selected_identities_remain_null(self) -> None:
        identities = assert_null_selection(IDENTITIES_PATH)
        self.assertFalse(identities.valid_for_official_use)

    def test_registry_hash_mismatch_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
            payload["canonical_hash"] = "0" * 64
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            with self.assertRaises(BaseModelRegistryError):
                load_base_model_candidate_registry(path)


if __name__ == "__main__":
    unittest.main()
