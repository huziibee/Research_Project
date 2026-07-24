"""T27E ambiguity-only recovery contracts and forensic helpers."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex


POLICY_REL = "configs/model/t27e_ambiguity_recovery_v1.json"
AMBIGUITY_TYPES = [
    "referential", "spatial", "pragmatic", "temporal", "quantitative",
    "preference", "commonsense", "safety_precondition", "capability", "contextual",
]


def build_minimal_ambiguity_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "t27e://predict_ambiguity_v1_minimal",
        "type": "object",
        "additionalProperties": False,
        "required": ["ambiguity_present", "ambiguity_types"],
        "properties": {
            "ambiguity_present": {"type": "boolean"},
            "ambiguity_types": {"type": "array", "items": {"type": "string", "enum": AMBIGUITY_TYPES}},
        },
    }


def effective_ambiguity_task_spec(registry: Mapping[str, Any]) -> dict[str, Any]:
    # Compatibility name retained for historical T27E diagnostics.  The
    # canonical layer now applies this contract for every entry point.
    from ambiguity_manager.model.generation_schema import effective_task_registry

    canonical = effective_task_registry()
    for task in canonical.get("tasks", []):
        if task.get("task_id") == "predict_ambiguity_v1":
            return copy.deepcopy(task)
    for original in registry.get("tasks", []):
        if original.get("task_id") == "predict_ambiguity_v1":
            task = copy.deepcopy(original)
            task["json_schema"] = build_minimal_ambiguity_schema()
            task["required_fields"] = ["ambiguity_present", "ambiguity_types"]
            task["optional_fields"] = []
            task["owned_production_fields"] = ["ambiguity_present", "ambiguity_types"]
            task["stable_field_order"] = ["ambiguity_present", "ambiguity_types"]
            task["maximum_output_tokens"] = 96
            task["prompt_contract_identity"] = "t27e_task_prompt_v1/predict_ambiguity_v1_minimal"
            return task
    raise ValueError("predict_ambiguity_v1 missing from task registry")


def ambiguity_forensic_summary(
    *, raw_text: str, maximum_output_tokens: int, generated_token_count: int,
    termination_reason: str,
) -> dict[str, Any]:
    stripped = raw_text.strip()
    depth = 0
    in_string = False
    escaped = False
    complete_at: int | None = None
    for index, char in enumerate(stripped):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth == 0 and complete_at is None:
                complete_at = index + 1
    complete = complete_at is not None and not in_string and depth == 0
    if not complete and termination_reason in {"length", "max_tokens", "maximum_token"}:
        termination_class = "bounded_maximum_token_unterminated_json"
    elif complete:
        termination_class = "complete_json"
    else:
        termination_class = "other_incomplete_json"
    return {
        "raw_prefix": stripped[:160],
        "raw_suffix": stripped[-160:],
        "raw_length_chars": len(raw_text),
        "json_complete": complete,
        "json_complete_char_offset": complete_at,
        "remaining_json_depth": depth,
        "generated_token_count": int(generated_token_count),
        "maximum_output_tokens": int(maximum_output_tokens),
        "termination_reason": termination_reason,
        "termination_class": termination_class,
    }


def validate_t27e_policy(policy: Mapping[str, Any]) -> None:
    if policy.get("config_id") != "t27e_ambiguity_recovery_v1":
        raise ValueError("wrong T27E policy")
    if policy.get("base_model") != "Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218":
        raise ValueError("immutable base mismatch")
    if policy.get("selected_adapter") is not None or policy.get("selected_model_strategy") is not None:
        raise ValueError("selection identities must remain null")
    if policy.get("valid_for_official_use") is not False:
        raise ValueError("official-use identity must remain false")
    if policy.get("sealed", {}).get("frozen_before_execution") is not True:
        raise ValueError("sealed policy must be frozen before execution")
    if policy.get("data_isolation", {}).get("protected_access_permitted") is not False:
        raise ValueError("protected access is forbidden")
    repair = policy.get("repair", {})
    if repair.get("task") != "predict_ambiguity_v1" or repair.get("other_tasks_enabled") is not False:
        raise ValueError("T27E must be ambiguity-only")
    if repair.get("ambiguity_training", {}).get("minimum_full_traversals") != 1:
        raise ValueError("full ambiguity traversal is required")


def policy_hash(root: Path) -> str:
    payload = json.loads((root / POLICY_REL).read_text(encoding="utf-8"))
    return sha256_hex(canonical_json_bytes(payload))
