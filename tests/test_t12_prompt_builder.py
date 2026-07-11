"""Tests for T12 Stage D1A prompt message contract."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.model.prediction_contract import (
    build_model_semantic_output_schema,
    model_semantic_output_schema_hash,
    runner_owned_prediction_fields,
)
from ambiguity_manager.model.prompt_builder import (
    PromptBuildRequest,
    build_prompt_messages,
    compute_prompt_hash,
)
from ambiguity_manager.schema.v2.taxonomies import (
    AmbiguityType,
    CapabilityStatus,
    CPCSlotStatus,
    RiskLevel,
    RouteLabel,
    SafetyStatus,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SYSTEM_TEMPLATE = REPO_ROOT / "configs" / "model" / "prompts" / "t12_schema_v2_system.md"
FORBIDDEN_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "schema_v2" / "t12_synthetic_inputs.jsonl"


class T12PromptBuilderTests(unittest.TestCase):
    def _request(self, **overrides: object) -> PromptBuildRequest:
        defaults = {
            "command": "Turn on the desk lamp.",
            "scene_context": "office with one desk lamp on the table",
            "dialogue_history": ["User: Can you help?", "Robot: Yes."],
            "capability_context": "robot can toggle lamps",
        }
        defaults.update(overrides)
        return PromptBuildRequest(**defaults)

    def test_deterministic_message_output(self) -> None:
        request = self._request()
        first = build_prompt_messages(request)
        second = build_prompt_messages(request)
        self.assertEqual(first, second)

    def test_deterministic_prompt_hash(self) -> None:
        request = self._request()
        first = compute_prompt_hash(request)
        second = compute_prompt_hash(request)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_message_roles_are_system_and_user_only(self) -> None:
        messages = build_prompt_messages(self._request())
        roles = {message["role"] for message in messages}
        self.assertEqual(roles, {"system", "user"})

    def test_no_context_role(self) -> None:
        messages = build_prompt_messages(self._request())
        roles = [message["role"] for message in messages]
        self.assertNotIn("context", roles)

    def test_exact_command_preserved(self) -> None:
        command = "Move that thing over there after a while."
        messages = build_prompt_messages(self._request(command=command))
        user_content = next(message["content"] for message in messages if message["role"] == "user")
        self.assertIn("[ORIGINAL_COMMAND]", user_content)
        self.assertIn(command, user_content)

    def test_optional_context_in_user_message_deterministically(self) -> None:
        messages = build_prompt_messages(self._request())
        user_content = next(message["content"] for message in messages if message["role"] == "user")
        self.assertIn("[SCENE_CONTEXT]", user_content)
        self.assertIn("[DIALOGUE_HISTORY]", user_content)
        self.assertIn("[CAPABILITY_CONTEXT]", user_content)
        self.assertIn("- User: Can you help?", user_content)
        self.assertIn("- Robot: Yes.", user_content)

    def test_absence_of_context_does_not_add_fake_context(self) -> None:
        messages = build_prompt_messages(
            self._request(scene_context=None, capability_context=None, dialogue_history=[]),
        )
        user_content = next(message["content"] for message in messages if message["role"] == "user")
        self.assertIn("[ORIGINAL_COMMAND]", user_content)
        self.assertNotIn("[SCENE_CONTEXT]", user_content)
        self.assertNotIn("[DIALOGUE_HISTORY]", user_content)
        self.assertNotIn("[CAPABILITY_CONTEXT]", user_content)

    def test_complete_model_schema_in_prompt(self) -> None:
        messages = build_prompt_messages(self._request())
        system_content = next(message["content"] for message in messages if message["role"] == "system")
        schema = build_model_semantic_output_schema()
        export = {key: value for key, value in schema.items() if not key.startswith("_")}
        compact = json.dumps(export, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertIn(compact, system_content)
        for required in schema["required"]:
            self.assertIn(f'"{required}"', system_content)

    def test_prompt_schema_hash_matches_generated_schema_hash(self) -> None:
        messages = build_prompt_messages(self._request())
        system_content = next(message["content"] for message in messages if message["role"] == "system")
        self.assertIn(model_semantic_output_schema_hash(), system_content)

    def test_cpc_status_and_safety_enums_appear(self) -> None:
        messages = build_prompt_messages(self._request())
        system_content = next(message["content"] for message in messages if message["role"] == "system")
        for status in CPCSlotStatus:
            self.assertIn(status.value, system_content)
        for safety in SafetyStatus:
            self.assertIn(safety.value, system_content)

    def test_route_and_taxonomy_enums_appear(self) -> None:
        messages = build_prompt_messages(self._request())
        system_content = next(message["content"] for message in messages if message["role"] == "system")
        for route in RouteLabel:
            self.assertIn(route.value, system_content)
        for risk in RiskLevel:
            self.assertIn(risk.value, system_content)
        for capability in CapabilityStatus:
            self.assertIn(capability.value, system_content)
        for ambiguity in AmbiguityType:
            self.assertIn(ambiguity.value, system_content)

    def test_label_eligibility_absent_from_prompt(self) -> None:
        messages = build_prompt_messages(self._request())
        system_content = next(message["content"] for message in messages if message["role"] == "system")
        self.assertNotIn("label_eligibility", system_content)

    def test_runner_owned_fields_not_in_model_schema_properties(self) -> None:
        messages = build_prompt_messages(self._request())
        system_content = next(message["content"] for message in messages if message["role"] == "system")
        marker = "Model-facing JSON Schema (complete; no omissions):"
        schema_text = system_content.split(marker, 1)[1].split("\n\nModel-facing schema hash:", 1)[0].strip()
        schema = json.loads(schema_text)
        overlap = runner_owned_prediction_fields() & set(schema["properties"])
        self.assertEqual(overlap, set())

    def test_output_only_rule_present(self) -> None:
        messages = build_prompt_messages(self._request())
        system_content = next(message["content"] for message in messages if message["role"] == "system")
        lowered = system_content.lower()
        self.assertIn("json", lowered)
        self.assertIn("schema", lowered)

    def test_no_markdown_fence_request(self) -> None:
        messages = build_prompt_messages(self._request())
        system_content = next(message["content"] for message in messages if message["role"] == "system")
        self.assertNotIn("```", system_content)

    def test_no_stage_d_runtime_parameter_guess(self) -> None:
        messages = build_prompt_messages(self._request())
        combined = "\n".join(message["content"] for message in messages).lower()
        for forbidden in (
            "temperature",
            "top_p",
            "max_new_tokens",
            "thinking",
            "enable_thinking",
            "guided_json",
            "guided_decoding",
        ):
            self.assertNotIn(forbidden, combined)

    def test_no_research_fixture_file_used(self) -> None:
        source = Path(__file__).resolve().parents[1] / "src" / "ambiguity_manager" / "model" / "prompt_builder.py"
        text = source.read_text(encoding="utf-8")
        self.assertNotIn("t12_synthetic_inputs.jsonl", text)

    def test_system_template_exists(self) -> None:
        self.assertTrue(SYSTEM_TEMPLATE.is_file())

    def test_prompt_builder_module_import_isolation(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "ambiguity_manager"
            / "model"
            / "prompt_builder.py"
        ).read_text(encoding="utf-8")
        for forbidden in ("import torch", "import transformers", "import vllm"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
