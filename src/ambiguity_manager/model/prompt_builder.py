"""Deterministic schema-v2 prompt message builder for T12 cluster inference."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.prediction_contract import (
    model_semantic_output_schema_for_prompt,
    model_semantic_output_schema_hash,
    runner_owned_prediction_fields,
)
from ambiguity_manager.schema.v2.taxonomies import (
    CapabilityStatus,
    RiskLevel,
)

SYSTEM_TEMPLATE_REL = Path("configs") / "model" / "prompts" / "t12_schema_v2_system.md"


@dataclass(frozen=True)
class PromptBuildRequest:
    command: str
    scene_context: str | None = None
    dialogue_history: list[str] = field(default_factory=list)
    capability_context: str | None = None


def _repo_root() -> Path:
    from ambiguity_manager.paths import repo_root

    return repo_root()


def _load_system_template() -> str:
    path = _repo_root() / SYSTEM_TEMPLATE_REL
    return path.read_text(encoding="utf-8")


def _risk_capability_definitions() -> str:
    return "\n".join(
        [
            "risk_level meanings:",
            "- none: no meaningful task risk identified",
            "- low: minor reversible risk",
            "- medium: meaningful risk requiring caution",
            "- high: serious harm or safety-sensitive risk",
            "- unknown: risk relevance unclear from available text",
            "",
            "capability_status meanings:",
            "- capable: robot can perform the requested action as interpreted",
            "- conditional: capable only under stated constraints",
            "- incapable: robot cannot perform the requested action",
            "- unknown: capability cannot be determined from available text",
        ]
    )


def build_system_message() -> str:
    template = _load_system_template()
    return (
        template.replace("{{MODEL_SCHEMA_JSON}}", model_semantic_output_schema_for_prompt())
        .replace("{{MODEL_SCHEMA_HASH}}", model_semantic_output_schema_hash())
        .replace("{{RISK_CAPABILITY_DEFINITIONS}}", _risk_capability_definitions())
        .replace(
            "{{RUNNER_OWNED_FIELD_COUNT}}",
            str(len(runner_owned_prediction_fields())),
        )
        .strip()
    )


def _build_user_content(request: PromptBuildRequest) -> str:
    sections: list[str] = ["[ORIGINAL_COMMAND]", request.command]
    if request.scene_context is not None:
        sections.extend(["", "[SCENE_CONTEXT]", request.scene_context])
    if request.dialogue_history:
        sections.extend(["", "[DIALOGUE_HISTORY]"])
        for line in request.dialogue_history:
            sections.append(f"- {line}")
    if request.capability_context is not None:
        sections.extend(["", "[CAPABILITY_CONTEXT]", request.capability_context])
    return "\n".join(sections)


def build_prompt_messages(request: PromptBuildRequest) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": build_system_message()},
        {"role": "user", "content": _build_user_content(request)},
    ]


def compute_prompt_hash(request: PromptBuildRequest) -> str:
    messages = build_prompt_messages(request)
    payload = [{"role": item["role"], "content": item["content"]} for item in messages]
    return sha256_hex(canonical_json_bytes({"messages": payload}))
