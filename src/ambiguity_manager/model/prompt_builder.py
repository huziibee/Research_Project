"""Build ModelClient messages from T12 synthetic fixtures."""

from __future__ import annotations

import json
from typing import Any

from ambiguity_manager.model.errors import ModelClientError


def build_schema_prompt_instruction(json_schema: dict[str, Any]) -> str:
    """Compact deterministic schema instruction derived from prediction-only schema."""
    record_class = json_schema.get("properties", {}).get("record_class", {})
    const = record_class.get("const", "prediction")
    payload = {
        "schema_id": json_schema.get("$id"),
        "schema_version": json_schema.get("schema_version"),
        "record_class": const,
        "required_fields": json_schema.get("required", []),
        "conditional_requirements": json_schema.get("description", ""),
        "output_format": "single_json_object_no_markdown",
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def build_messages_from_fixture(
    fixture: dict[str, Any],
    *,
    json_schema: dict[str, Any],
) -> list[dict[str, str]]:
    fixture_id = fixture.get("fixture_id")
    command = fixture.get("command")
    if not isinstance(fixture_id, str) or not fixture_id:
        raise ModelClientError("fixture_id required")
    if not isinstance(command, str) or not command.strip():
        raise ModelClientError("fixture command required")

    scene_context = fixture.get("scene_context") or ""
    capability_context = fixture.get("capability_context") or ""
    dialogue_history = fixture.get("dialogue_history") or []
    if not isinstance(dialogue_history, list):
        raise ModelClientError("dialogue_history must be a list")

    dialogue_text = "\n".join(str(item) for item in dialogue_history if item)
    schema_text = build_schema_prompt_instruction(json_schema)

    system_parts = [
        "You are an ambiguity-aware household robot command interpreter.",
        "Respond with one JSON object matching the provided schema.",
        "Do not include markdown fences or commentary outside the JSON object.",
        f"Schema instruction:\n{schema_text}",
    ]
    user_parts = [f"Command: {command}"]
    if scene_context:
        user_parts.append(f"Scene context: {scene_context}")
    if capability_context:
        user_parts.append(f"Capability context: {capability_context}")
    if dialogue_text:
        user_parts.append(f"Dialogue history:\n{dialogue_text}")

    return [
        {"role": "system", "content": "\n\n".join(system_parts)},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]
