"""Tests for T12 Stage D1C1 repair prompt contract."""

from __future__ import annotations

import copy
import unittest

from ambiguity_manager.model.prediction_contract import model_semantic_output_schema_hash
from ambiguity_manager.model.prompt_builder import PromptBuildRequest
from ambiguity_manager.model.repair_prompt import (
    RepairPromptRequest,
    build_repair_prompt,
    load_pipeline_contract,
)


class T12RepairPromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_pipeline_contract()

    def _request(self) -> PromptBuildRequest:
        return PromptBuildRequest(
            command="Pick up the cup.",
            scene_context="two cups on the counter",
            dialogue_history=["Which one?"],
            capability_context="robot can pick up cups",
        )

    def test_original_command_preserved_exactly(self) -> None:
        request = self._request()
        result = build_repair_prompt(
            RepairPromptRequest(
                original_request=request,
                attempt_number=1,
                validation_failures=("schema validation failed",),
            ),
            contract=self.contract,
        )
        self.assertIn("Pick up the cup.", result.repair_user_content)

    def test_context_preserved(self) -> None:
        request = self._request()
        result = build_repair_prompt(
            RepairPromptRequest(
                original_request=request,
                attempt_number=1,
                validation_failures=("parse failed",),
            ),
            contract=self.contract,
        )
        self.assertIn("two cups on the counter", result.repair_user_content)
        self.assertIn("Which one?", result.repair_user_content)
        self.assertIn("robot can pick up cups", result.repair_user_content)

    def test_schema_hash_unchanged(self) -> None:
        result = build_repair_prompt(
            RepairPromptRequest(
                original_request=self._request(),
                attempt_number=1,
                validation_failures=("invalid enum",),
            ),
            contract=self.contract,
        )
        self.assertEqual(result.schema_hash, model_semantic_output_schema_hash())

    def test_only_prior_validation_errors_included(self) -> None:
        failures = ("json parse failed", "missing required field: cpc")
        result = build_repair_prompt(
            RepairPromptRequest(
                original_request=self._request(),
                attempt_number=2,
                validation_failures=failures,
            ),
            contract=self.contract,
        )
        for failure in failures:
            self.assertIn(failure, result.repair_user_content)

    def test_attempt_number_included(self) -> None:
        result = build_repair_prompt(
            RepairPromptRequest(
                original_request=self._request(),
                attempt_number=2,
                validation_failures=("schema invalid",),
            ),
            contract=self.contract,
        )
        self.assertIn("attempt_number=2", result.repair_user_content)

    def test_complete_replacement_required(self) -> None:
        result = build_repair_prompt(
            RepairPromptRequest(
                original_request=self._request(),
                attempt_number=1,
                validation_failures=("invalid",),
            ),
            contract=self.contract,
        )
        self.assertIn("complete replacement semantic JSON object", result.repair_user_content)

    def test_prompt_deterministic(self) -> None:
        req = RepairPromptRequest(
            original_request=self._request(),
            attempt_number=1,
            validation_failures=("parse failed",),
            prior_raw_output='{"bad": true}',
        )
        first = build_repair_prompt(req, contract=self.contract)
        second = build_repair_prompt(req, contract=self.contract)
        self.assertEqual(first.repair_user_content, second.repair_user_content)

    def test_prompt_hash_deterministic(self) -> None:
        req = RepairPromptRequest(
            original_request=self._request(),
            attempt_number=1,
            validation_failures=("parse failed",),
        )
        first = build_repair_prompt(req, contract=self.contract)
        second = build_repair_prompt(req, contract=self.contract)
        self.assertEqual(first.repair_prompt_hash, second.repair_prompt_hash)
        self.assertEqual(len(first.repair_prompt_hash), 64)

    def test_caller_input_not_mutated(self) -> None:
        request = self._request()
        snapshot = copy.deepcopy(request)
        build_repair_prompt(
            RepairPromptRequest(
                original_request=request,
                attempt_number=1,
                validation_failures=("invalid",),
                prior_raw_output="x" * 5000,
            ),
            contract=self.contract,
        )
        self.assertEqual(request, snapshot)

    def test_prior_raw_output_truncation_recorded(self) -> None:
        long_output = "z" * 5000
        result = build_repair_prompt(
            RepairPromptRequest(
                original_request=self._request(),
                attempt_number=1,
                validation_failures=("invalid",),
                prior_raw_output=long_output,
            ),
            contract=self.contract,
        )
        self.assertTrue(result.prior_raw_output_truncated)
        self.assertTrue(result.prior_raw_output_included)
        self.assertLessEqual(
            len(result.repair_user_content),
            len(long_output) + 2000,
        )


if __name__ == "__main__":
    unittest.main()
