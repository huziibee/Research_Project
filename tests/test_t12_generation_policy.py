"""Tests for T12 Stage D1A generation and repair policy contract."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.model.generation_policy import (
    ACCEPTANCE_RULE_IDS,
    T19_ROUTING_DEFERRED,
    load_generation_policy,
)
from ambiguity_manager.model.parser import MAX_REPAIR_ROUNDS

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "configs" / "model" / "t12_generation_policy.json"


class T12GenerationPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_generation_policy(POLICY_PATH)

    def test_policy_file_exists(self) -> None:
        self.assertTrue(POLICY_PATH.is_file())

    def test_total_attempts_equal_initial_plus_regeneration(self) -> None:
        self.assertEqual(
            self.policy.total_model_attempts,
            self.policy.initial_generation_attempts + self.policy.bounded_regeneration_attempts,
        )

    def test_no_unconstrained_fallback(self) -> None:
        self.assertFalse(self.policy.unconstrained_fallback_permitted)

    def test_raw_attempt_retention_required(self) -> None:
        self.assertTrue(self.policy.retain_all_raw_attempts)

    def test_structural_and_semantic_metrics_separate(self) -> None:
        self.assertTrue(self.policy.structural_validity_separate_from_semantic_correctness)

    def test_repair_rounds_match_parser_limit(self) -> None:
        self.assertEqual(
            self.policy.deterministic_local_json_repair_rounds,
            MAX_REPAIR_ROUNDS,
        )

    def test_expected_attempt_boundaries(self) -> None:
        self.assertEqual(self.policy.total_model_attempts, 3)
        self.assertEqual(self.policy.initial_generation_attempts, 1)
        self.assertEqual(self.policy.bounded_regeneration_attempts, 2)

    def test_t19_routing_explicitly_deferred(self) -> None:
        self.assertTrue(T19_ROUTING_DEFERRED)
        self.assertTrue(self.policy.full_t19_routing_deferred)

    def test_acceptance_rule_ids_present(self) -> None:
        expected = {
            "canonical_schema_validation",
            "schema_route_conditional_checks",
            "unsupported_silent_commitment_checks",
            "invalid_enum_rejection",
            "malformed_nested_structure_rejection",
        }
        self.assertEqual(set(ACCEPTANCE_RULE_IDS), expected)
        self.assertEqual(set(self.policy.acceptance_rule_ids), expected)

    def test_schema_invalid_never_accepted(self) -> None:
        self.assertFalse(self.policy.accept_schema_invalid_output)

    def test_exhausted_attempts_explicit_rejection(self) -> None:
        self.assertTrue(self.policy.exhausted_attempts_end_in_explicit_rejection)


if __name__ == "__main__":
    unittest.main()
