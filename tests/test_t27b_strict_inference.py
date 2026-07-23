"""T27B strict inference prompt + multi-stage validation tests (CPU-only)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.model.full_schema_envelope import (  # noqa: E402
    build_full_schema_envelope,
    load_envelope_policy,
)
from ambiguity_manager.model.structured_output_validation import (  # noqa: E402
    validate_structured_model_output,
)
from ambiguity_manager.model.t27b_prompt_contract import (  # noqa: E402
    PROMPT_CONTRACT_ID,
    build_t27b_inference_prompt,
)
from ambiguity_manager.model.t27b_structured_validation import (  # noqa: E402
    validate_t27b_structured_model_output,
)
from ambiguity_manager.model.training_target_packaging import (  # noqa: E402
    load_training_target_policy_strict,
)


def _sample_record() -> dict:
    path = ROOT / "data/development/t27b_final_smoke_v1/records.jsonl"
    return json.loads(path.read_text(encoding="utf-8").splitlines()[0])["record"]


class T27BStrictInferenceTests(unittest.TestCase):
    def test_prompt_requests_full_schema_without_json_schema_document(self) -> None:
        prompt = build_t27b_inference_prompt(_sample_record())
        self.assertIn(PROMPT_CONTRACT_ID, prompt)
        self.assertIn("t12_model_semantic_output", prompt)
        self.assertIn("ambiguity_present", prompt)
        self.assertIn("Do NOT emit JSON Schema meta-keys", prompt)
        self.assertNotIn('"properties"', prompt)
        self.assertNotIn('"$schema"', prompt)
        self.assertNotIn('"additionalProperties"', prompt)
        self.assertIn("$schema", prompt)  # listed only as a forbidden meta-key warning
        self.assertNotIn("label_eligibility", prompt)
        self.assertNotIn("design_cell", prompt)
        self.assertNotIn("source_train", prompt)

    def test_schema_echo_classified_unknown_field(self) -> None:
        prompt = build_t27b_inference_prompt(_sample_record())
        verdict = validate_t27b_structured_model_output(
            prompt=prompt,
            raw_output='{"properties": {}, "required": [], "type": "object"}',
        )
        self.assertEqual(verdict.failure_stage, "unknown_field")
        self.assertFalse(verdict.accepted)
        self.assertEqual(verdict.schema_status, "invalid")

    def test_no_json_and_braces_only(self) -> None:
        prompt = "PROMPT"
        no_json = validate_t27b_structured_model_output(prompt=prompt, raw_output="hello world")
        self.assertEqual(no_json.failure_stage, "no_json")
        braces = validate_t27b_structured_model_output(prompt=prompt, raw_output="{not json")
        self.assertIn(braces.failure_stage, {"json_parse_failed", "truncation", "no_json"})
        legacy = validate_structured_model_output(prompt=prompt, raw_output="{ }")
        self.assertFalse(legacy.accepted)

    def test_valid_envelope_accepted_through_stages(self) -> None:
        row = json.loads(
            (ROOT / "data/development/qlora_structured_emission_recovery_v1/records.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()[0]
        )
        policy = load_envelope_policy(ROOT / "configs/model/full_schema_envelope_policy_v1.json")
        training = load_training_target_policy_strict(
            ROOT / "configs/data/training_target_policy_v1.json"
        )
        envelope = build_full_schema_envelope(
            row["record"], row["eligibility"], policy=policy, training_policy=training
        )
        prompt = build_t27b_inference_prompt(row["record"])
        verdict = validate_t27b_structured_model_output(
            prompt=prompt, raw_output=prompt + "\n" + envelope.canonical_json
        )
        self.assertTrue(verdict.accepted)
        self.assertEqual(verdict.json_parse_status, "parsed")
        self.assertEqual(verdict.schema_status, "valid")
        self.assertEqual(verdict.semantic_status, "valid")
        self.assertEqual(verdict.safety_status, "accepted")
        self.assertEqual(verdict.final_acceptance_status, "accepted")

    def test_constrained_syntax_alone_not_acceptance(self) -> None:
        # Partial object with braces is not acceptance.
        prompt = build_t27b_inference_prompt(_sample_record())
        verdict = validate_t27b_structured_model_output(
            prompt=prompt, raw_output='{"ambiguity_present": true}'
        )
        self.assertFalse(verdict.accepted)
        self.assertEqual(verdict.failure_stage, "missing_required_field")


if __name__ == "__main__":
    unittest.main()
