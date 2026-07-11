"""Tests for T12 Stage D1C1 repair prompt contract."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from ambiguity_manager.model.prediction_contract import model_semantic_output_schema_hash
from ambiguity_manager.model.prompt_builder import PromptBuildRequest
from ambiguity_manager.model.repair_prompt import (
    RepairPromptRequest,
    build_repair_prompt,
    generation_pipeline_contract_hash,
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


class T12GenerationPipelineContractHashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract_path = (
            Path(__file__).resolve().parents[1]
            / "configs/model/t12_generation_pipeline_contract.json"
        )
        cls.contract = load_pipeline_contract(cls.contract_path)
        cls.canonical_hash = "786cf6e7213fa3519ba7797464c25495f790cdf4ebc0c139c433168bd703b758"

    def test_lf_and_crlf_raw_bytes_differ_but_parse_equally(self) -> None:
        from ambiguity_manager.governance.hashing import sha256_hex

        raw = self.contract_path.read_bytes()
        lf = raw.replace(b"\r\n", b"\n")
        crlf = lf.replace(b"\n", b"\r\n")
        self.assertEqual(
            json.loads(lf.decode("utf-8")),
            json.loads(crlf.decode("utf-8")),
        )
        self.assertEqual(
            sha256_hex(lf),
            "94eb2d777fb6e9bbebc90b7c8d727cec2e2bebfcf0acbcd276144f2c71d34b64",
        )
        self.assertEqual(
            sha256_hex(crlf),
            "1c4543e29121ce1e390ea60d91c51530cb180f8624d1e7932c4d9524a186599b",
        )

    def test_canonical_hash_matches_expected(self) -> None:
        self.assertEqual(generation_pipeline_contract_hash(self.contract_path), self.canonical_hash)
        self.assertEqual(generation_pipeline_contract_hash(self.contract), self.canonical_hash)

    def test_reordered_keys_same_hash(self) -> None:
        reordered = dict(sorted(self.contract.items(), key=lambda item: item[0], reverse=True))
        self.assertEqual(generation_pipeline_contract_hash(reordered), self.canonical_hash)

    def test_indentation_change_same_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.json"
            path.write_text(json.dumps(self.contract, indent=4) + "\n", encoding="utf-8")
            self.assertEqual(generation_pipeline_contract_hash(path), self.canonical_hash)

    def test_semantic_mutation_changes_hash(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["contract_version"] = "9.9.9"
        self.assertNotEqual(generation_pipeline_contract_hash(mutated), self.canonical_hash)


if __name__ == "__main__":
    unittest.main()
