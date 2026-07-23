"""T27B inference/training prompt contract (full production schema).

CPU-only. Does not embed the full JSON Schema document (that caused schema-echo
in job 6059). Lists required field names and compact type/enum constraints.
"""

from __future__ import annotations

from typing import Any, Mapping

from ambiguity_manager.model.full_schema_envelope import PROMPT_CONTRACT_VERSION
from ambiguity_manager.model.prediction_contract import MODEL_OUTPUT_REQUIRED_FIELDS
from ambiguity_manager.schema.v2.taxonomies import (
    AmbiguityType,
    CapabilityStatus,
    RiskLevel,
    RouteLabel,
)
from ambiguity_manager.systems.contracts import INTENT_LABELS

PROMPT_CONTRACT_ID = "t27b_full_schema_prompt_v1"


class T27BPromptContractError(RuntimeError):
    """Raised when a T27B prompt cannot be built safely."""


def _compact_field_guide() -> str:
    routes = "|".join(item.value for item in RouteLabel)
    risks = "|".join(item.value for item in RiskLevel)
    caps = "|".join(item.value for item in CapabilityStatus)
    amb = "|".join(item.value for item in AmbiguityType)
    intents = "|".join(sorted(INTENT_LABELS))
    fields = ", ".join(sorted(MODEL_OUTPUT_REQUIRED_FIELDS))
    lines = [
        "Emit exactly one JSON object with ALL of these required keys "
        f"(no others): {fields}.",
        "Types/enums (compact):",
        f"- speech_act: null or [{intents}]",
        "- intent_summary: string|null",
        "- cpc: object with 13 slots "
        "(action,actor,object,object_attributes,destination,spatial_relation,"
        "quantity,time,recipient,tool,conditions,constraints,negation); "
        "each slot is {\"value\":..., \"status\": filled|missing|unknown|not_applicable}",
        "- candidate_interpretations: array of objects; selected_interpretation: object|null",
        "- unresolved_slots/supporting_evidence/resolved_slots/resolution_evidence: arrays",
        "- ambiguity_present/compound_ambiguity/risk_relevant: boolean",
        f"- ambiguity_types: array of [{amb}]; primary_ambiguity_type: one of those or null",
        "- compound_ambiguity_count: integer",
        f"- risk_level: null|[{risks}]; capability_status: null|[{caps}]",
        f"- recommended_strategy: [{routes}]; strategy_sequence: array of route labels "
        "(non-empty only for multi_step)",
        "- clarification_question/clarification_subtype/rejection_reason/"
        "resolution_method/context_sampling_uncertainty: string|null as schema allows",
        "- clarification_targets: string array",
        "Do NOT emit JSON Schema meta-keys (properties, required, type, $schema, items).",
        "Do NOT invent runner-owned or administrative fields.",
        "Bounded generation: return only the JSON object, no prose.",
    ]
    return "\n".join(lines)


def build_t27b_inference_prompt(record: Mapping[str, Any]) -> str:
    """Build a prompt requesting the full production semantic object.

    Identical contract for base and adapter. Must not include source labels,
    design-cell, eligibility, or sealed-set examples.
    """
    command = str(record.get("command") or "").strip()
    if not command:
        raise T27BPromptContractError("command_required_for_prompt")

    sections: list[str] = [
        "You are a structured semantic analyzer for compound ambiguous robot commands.",
        "Return exactly one JSON object and nothing else.",
        f"Prompt contract: {PROMPT_CONTRACT_VERSION} ({PROMPT_CONTRACT_ID}).",
        "Target schema: t12_model_semantic_output (full production semantic object).",
        "",
        "[ORIGINAL_COMMAND]",
        command,
    ]
    scene = record.get("scene_context")
    if isinstance(scene, str) and scene.strip():
        sections.extend(["", "[SCENE_CONTEXT]", scene.strip()])
    history = record.get("dialogue_history")
    if isinstance(history, list) and history:
        sections.extend(["", "[DIALOGUE_HISTORY]"])
        for line in history:
            if isinstance(line, str) and line.strip():
                sections.append(f"- {line.strip()}")
    capability = record.get("capability_context")
    if isinstance(capability, str) and capability.strip():
        sections.extend(["", "[CAPABILITY_CONTEXT]", capability.strip()])
    sections.extend(["", "[OUTPUT_SCHEMA_INSTRUCTIONS]", _compact_field_guide()])
    prompt = "\n".join(sections)
    for marker in ("[ELIGIBILITY", "split=", "design_cell=", "label_eligibility"):
        if marker in prompt:
            raise T27BPromptContractError(f"prompt_leaked_admin_marker:{marker}")
    return prompt
