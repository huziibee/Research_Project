"""Research contract validation."""

from __future__ import annotations

from typing import Any

from ambiguity_manager.governance.paths import is_absolute_machine_path

CONTRACT_SCHEMA_VERSION = "1.0.0"

MANDATORY_SYSTEM_IDS = [
    "always_execute",
    "always_clarify",
    "always_silently_resolve",
    "direct_base_llm",
    "degree_based_router",
    "context_blind_manager",
    "full_finetuned_type_risk_manager",
]

CANONICAL_ROUTES = [
    "execute",
    "clarify",
    "silently_resolve",
    "face_preserving_rejection",
    "multi_step",
]

CANONICAL_AMBIGUITY_LABELS = [
    "referential",
    "spatial",
    "pragmatic",
    "temporal",
    "quantitative",
    "preference",
    "commonsense",
    "safety_precondition",
    "capability",
    "contextual",
]

_HASH_FIELDS = frozenset({"content_hash", "content_hash_sha256", "sha256"})


def validate_research_contract(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if data.get("contract_schema_version") != CONTRACT_SCHEMA_VERSION:
        errors.append(f"contract_schema_version must be {CONTRACT_SCHEMA_VERSION}")

    for field_name in _HASH_FIELDS:
        if field_name in data:
            errors.append(f"research contract must not contain self-referential field {field_name!r}")

    for path_field in ("licence_authority",):
        authority = data.get(path_field)
        if isinstance(authority, dict):
            for key, value in authority.items():
                if isinstance(value, str) and is_absolute_machine_path(value):
                    errors.append(f"{path_field}.{key} must be repository-relative")

    systems = data.get("mandatory_systems")
    if not isinstance(systems, list):
        errors.append("mandatory_systems must be a list")
    else:
        if len(systems) != 7:
            errors.append("mandatory_systems must contain exactly seven systems")
        ids = []
        for index, entry in enumerate(systems):
            if not isinstance(entry, dict):
                errors.append(f"mandatory_systems[{index}] must be an object")
                continue
            system_id = entry.get("id")
            ids.append(system_id)
            if entry.get("optional") is not False:
                errors.append(f"mandatory_systems[{index}].optional must be false")
        if ids != MANDATORY_SYSTEM_IDS:
            errors.append("mandatory_systems ids must match canonical seven-system list")

    scope = data.get("scope", {})
    if scope.get("text_only") is not True:
        errors.append("scope.text_only must be true")
    if scope.get("raw_image_lvlm") is not False:
        errors.append("scope.raw_image_lvlm must be false")

    model_policy = data.get("model_policy", {})
    if model_policy.get("mandatory_supervised_finetuning") is not True:
        errors.append("model_policy.mandatory_supervised_finetuning must be true")
    if model_policy.get("finetuning_blocked_substitution") != "BLOCKED":
        errors.append("model_policy.finetuning_blocked_substitution must be BLOCKED")

    supersession = data.get("supersession", {})
    for field in ("proposal_dataset_section", "proposal_calendar_schedule"):
        if supersession.get(field) != "superseded":
            errors.append(f"supersession.{field} must be 'superseded'")

    if data.get("primary_outcome") != "routing_correctness":
        errors.append("primary_outcome must be routing_correctness")

    routes = data.get("canonical_routes")
    if routes != CANONICAL_ROUTES:
        errors.append("canonical_routes must match canonical five-route list")

    labels = data.get("canonical_ambiguity_labels")
    if labels != CANONICAL_AMBIGUITY_LABELS:
        errors.append("canonical_ambiguity_labels must match canonical ten-label list")

    evaluation = data.get("evaluation_policy", {})
    if evaluation.get("deterministic_evaluator_primary") is not True:
        errors.append("evaluation_policy.deterministic_evaluator_primary must be true")
    if evaluation.get("generative_llm_not_primary_judge") is not True:
        errors.append("evaluation_policy.generative_llm_not_primary_judge must be true")

    return errors
