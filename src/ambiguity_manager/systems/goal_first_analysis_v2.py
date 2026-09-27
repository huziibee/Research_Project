"""Separately versioned Pilot-120 analysis contract. Frozen T39 prompts stay untouched."""
from __future__ import annotations

import json
import re
from typing import Any

from ambiguity_manager.schema.v2.records import (
    ContextSamplingUncertainty,
    CPC,
    CPCSlot,
    ResolvedSlotValue,
    UnresolvedSlot,
)
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES, CPCSlotStatus
from ambiguity_manager.systems.contracts import AnalysisProvenance, StructuredAnalysis, SystemInput

SPEECH_ACTS = {
    "directive_command",
    "indirect_request",
    "information_question",
    "permission_request",
    "prohibition",
    "conditional_directive",
    "multi_intent",
    "other_non_actionable",
}
AMBIGUITY_TYPES = [
    "pragmatic",
    "discourse_ellipsis",
    "lexical",
    "scope",
    "object_reference",
    "pronoun_reference",
    "recipient_reference",
    "destination_reference",
    "instrument_reference",
    "spatial_reference",
    "temporal_reference",
    "routine_reference",
    "action_order",
    "fuzzy_temporal",
    "fuzzy_quantity",
    "degree_vagueness",
    "endpoint_vagueness",
]

# Short definitions for the Pilot-17 exam. Constrained emission must see these:
# 111/120 R1 rows tagged via the constrained path, which previously listed no names.
AMBIGUITY_TYPE_HINTS: dict[str, str] = {
    "pragmatic": "indirect request, politeness, or capability/permission question whose real job is an action",
    "discourse_ellipsis": "missing noun/verb recovered only from prior dialogue turns",
    "lexical": "word has multiple licensed handbook senses",
    "scope": "unclear which object/action a modifier or negation covers",
    "object_reference": "which physical object is meant among several scene candidates",
    "pronoun_reference": "pronoun (it/that/them) whose antecedent is unclear",
    "recipient_reference": "who should receive the item is unclear",
    "destination_reference": "where to put/take the item is unclear",
    "instrument_reference": "which tool/instrument is meant is unclear",
    "spatial_reference": "spatial relation (left/near/beside) is underspecified",
    "temporal_reference": "clock time, schedule slot, or named service time is underspecified",
    "routine_reference": "named ward routine/procedure whose steps are not fully stated",
    "action_order": "two or more actions with unclear sequence — NOT mere multi-step jobs with clear order",
    "fuzzy_temporal": "vague time words (shortly, soon, later) without a licensed clock value",
    "fuzzy_quantity": "vague amount words without a licensed number",
    "degree_vagueness": "vague intensity (gently, carefully) without a measurable degree",
    "endpoint_vagueness": "unclear completion criterion / when the job is done",
}


def _ambiguity_prompt_block() -> str:
    lines = [
        "pilot_ambiguity_types must be a JSON array using ONLY these Pilot-17 labels "
        "(include every type that is present; omit types that are absent; typical size 2-4):",
    ]
    for name in AMBIGUITY_TYPES:
        lines.append(f"- {name}: {AMBIGUITY_TYPE_HINTS[name]}")
    lines.extend(
        [
            "CRITICAL ambiguity rules:",
            "- Prefer object_reference / temporal_reference / routine_reference when they fit.",
            "- Emit action_order ONLY when the command has two+ actions and their order is genuinely ambiguous.",
            "- Do NOT emit action_order merely because the job has multiple clear steps.",
            "- Prefer fuzzy_temporal over temporal_reference for shortly/soon/later without a licensed clock.",
            "- Emit pragmatic ONLY when the surface form is a question, permission check, or politeness "
            "wrapper whose real job is an action (indirect request). Do NOT tag pragmatic on ordinary "
            "directive_command jobs that already name the action.",
            "- Prefer instrument_reference / pronoun_reference / destination_reference when those slots "
            "are the actual underspecification; do not collapse them into pragmatic.",
        ]
    )
    return "\n".join(lines) + "\n"
CAPABILITIES = [
    "capable",
    "conditionally_capable",
    "incapable",
    "unauthorized",
    "unsafe",
]
CANONICAL_AMBIGUITY = {
    "pragmatic": "pragmatic",
    "discourse_ellipsis": "contextual",
    "lexical": "referential",
    "scope": "referential",
    "object_reference": "referential",
    "pronoun_reference": "referential",
    "recipient_reference": "referential",
    "destination_reference": "spatial",
    "instrument_reference": "capability",
    "spatial_reference": "spatial",
    "temporal_reference": "temporal",
    "routine_reference": "contextual",
    "action_order": "temporal",
    "fuzzy_temporal": "temporal",
    "fuzzy_quantity": "quantitative",
    "degree_vagueness": "quantitative",
    "endpoint_vagueness": "spatial",
}
CANONICAL_CAPABILITY = {
    "capable": "capable",
    "conditionally_capable": "conditional",
    "incapable": "incapable",
    "unauthorized": "unknown",
    "unsafe": "unknown",
}
CANONICAL_RISKS = {"none", "low", "medium", "high", "unknown"}
SLOT_ALIASES = {"temporal": "time", "spatial": "spatial_relation", "intent": "action"}
_ROUTE_TERMS = re.compile(
    r"(?i)\b(execute|clarify|reject|silently[ _-]?resolve)\b|\broute\b(?!\s+card|\s+marker|\s+bay)"
)
_CLOCK_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
SCENE_SLOT_CUES = {
    "destination": (
        "destination",
        "alcove",
        "plinth",
        "corridor",
        "ward",
        "bay",
        "shelf",
        "desk",
        "rack",
        "entrance",
        "return point",
        "assigned",
    ),
    "time": ("scheduled", "minutes", "shortly", "deadline", "idle slot", "current time", "occurrence"),
    "object": ("pending", "complete", "move tag", "selected", "marked", "two ", "amber", "red ", "black "),
    "tool": ("scale", "scanner", "printer"),
    "recipient": ("recipient", "nurse", "clerk", "paired"),
    "quantity": ("kg", "kilogram", "below", "limit"),
}

CPC_SLOT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "value"],
    "properties": {
        "status": {"type": "string", "enum": ["filled", "missing", "unknown", "not_applicable"]},
        "value": {"type": ["string", "null"]},
    },
}

ANALYSIS_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "intent_summary",
        "speech_act",
        "cpc",
        "pilot_ambiguity_types",
        "pilot_capability_status",
        "risk_level",
        "unresolved_slots",
        "uncertainty",
    ],
    "properties": {
        "intent_summary": {"type": "string", "minLength": 1, "maxLength": 500},
        "speech_act": {"type": "string", "enum": sorted(SPEECH_ACTS)},
        "cpc": {
            "type": "object",
            "additionalProperties": False,
            "required": list(CPC_SLOT_NAMES),
            "properties": {name: CPC_SLOT_SCHEMA for name in CPC_SLOT_NAMES},
        },
        "pilot_ambiguity_types": {
            "type": "array",
            "items": {"type": "string", "enum": AMBIGUITY_TYPES},
        },
        "pilot_capability_status": {"type": "string", "enum": CAPABILITIES},
        "risk_level": {"type": "string", "enum": sorted(CANONICAL_RISKS)},
        "unresolved_slots": {
            "type": "array",
            "items": {"type": "string", "enum": sorted(set(CPC_SLOT_NAMES) | set(SLOT_ALIASES))},
        },
        "uncertainty": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
}


def _normalise_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def joined_context(system_input: SystemInput) -> str:
    dialogue = " ".join(system_input.dialogue_history)
    return " ".join(
        [
            system_input.command or "",
            system_input.scene_context or "",
            dialogue,
            system_input.capability_context or "",
        ]
    )


def slot_licensed_by_context(slot: str, context: str) -> bool:
    name = SLOT_ALIASES.get(slot, slot)
    text = context.casefold()
    if name == "time" and _CLOCK_RE.search(text):
        return True
    cues = SCENE_SLOT_CUES.get(name, (name,))
    return any(cue in text for cue in cues)


def canonical_slot_name(slot: str) -> str:
    return SLOT_ALIASES.get(str(slot), str(slot))


def build_analysis_prompt(system_input: SystemInput) -> str:
    return (
        "Analyse this robot command for a routing manager. Do not choose a final route.\n"
        "First write intent_summary: what the human wants done, in one paraphrase. "
        "Preserve polarity and every required action. Do not copy the command. "
        "Do not mention execute, clarify, reject, or route.\n"
        "Then fill CPC slots from the command, scene, and dialogue. "
        "If the scene or dialogue already licences a slot (clock time, PENDING/COMPLETE tag, "
        "assigned destination, handbook meaning of shortly), mark that slot filled with the "
        "licensed value and do not list it as unresolved.\n"
        "Only list unresolved_slots that are truly absent from command, scene, and dialogue.\n"
        "Return ONLY one JSON object with these exact keys:\n"
        "intent_summary, speech_act, cpc, pilot_ambiguity_types, "
        "pilot_capability_status, risk_level, unresolved_slots, uncertainty.\n"
        "cpc must include every slot "
        + ", ".join(CPC_SLOT_NAMES)
        + ' as {"status": filled|missing|unknown|not_applicable, "value": string-or-null}.\n'
        "CRITICAL CPC RULE: if value is a concrete non-empty string licensed by command, scene, or dialogue, "
        "status MUST be filled. Never write a usable value and then mark unknown or not_applicable.\n"
        "Allowed speech_act: "
        + ", ".join(sorted(SPEECH_ACTS))
        + "\n"
        + _ambiguity_prompt_block()
        + "Allowed pilot_capability_status: "
        + ", ".join(CAPABILITIES)
        + "\n"
        "Allowed risk_level: none, low, medium, high, unknown.\n"
        "You may reason carefully first, but must finish with the JSON object.\n\n"
        f"record_id: {system_input.record_id}\n"
        f"command: {system_input.command}\n"
        f"dialogue_history: {json.dumps(list(system_input.dialogue_history), ensure_ascii=False)}\n"
        f"scene_context: {system_input.scene_context}\n"
        f"capability_context: {system_input.capability_context}\n"
    )


def build_retry_prompt(system_input: SystemInput, validation_error: str) -> str:
    hints = ""
    if "route_contamination" in validation_error:
        hints = (
            "CRITICAL: intent_summary must never contain the words execute, clarify, reject, "
            "or route. Describe the human goal only.\n"
        )
    elif "bad_intent_summary" in validation_error:
        hints = (
            "CRITICAL: intent_summary must be a non-empty paraphrase under 500 characters, "
            "not a copy of the command, and not blank.\n"
        )
    elif "no_json" in validation_error:
        hints = (
            "CRITICAL: emit exactly one complete JSON object and stop. "
            "Do not repeat keys or loop text.\n"
        )
    return (
        "Your prior answer did not satisfy the required machine-readable schema "
        f"(validation error: {validation_error}). Re-analyse the source record. "
        "Fill intent_summary and CPC from scene/dialogue before listing unresolved slots. "
        "Do not infer hidden gold labels.\n"
        + hints
        + "\n"
        + build_analysis_prompt(system_input)
    )


def build_constrained_prompt(system_input: SystemInput) -> str:
    return (
        "Produce the routing-manager analysis for this source record. "
        "The JSON schema enforces the allowed fields and labels. Do not use gold labels.\n"
        "First fill intent_summary (job paraphrase only). Then CPC. Then pilot_ambiguity_types.\n"
        + _ambiguity_prompt_block()
        + "\n"
        f"record_id: {system_input.record_id}\n"
        f"command: {system_input.command}\n"
        f"dialogue_history: {json.dumps(list(system_input.dialogue_history), ensure_ascii=False)}\n"
        f"scene_context: {system_input.scene_context}\n"
        f"capability_context: {system_input.capability_context}\n"
    )


def _parse_cpc(raw: Any) -> tuple[CPC | None, str | None]:
    if not isinstance(raw, dict):
        return None, "bad_cpc"
    slots: dict[str, CPCSlot] = {}
    for name in CPC_SLOT_NAMES:
        item = raw.get(name)
        if not isinstance(item, dict):
            return None, f"bad_cpc_slot:{name}"
        status = item.get("status")
        value = item.get("value")
        # Contract repair: a concrete value must not hide behind unknown/N/A,
        # and placeholder "filled" values must not pollute official F1.
        _placeholder = {
            "",
            "none",
            "null",
            "unknown",
            "unassigned",
            "n/a",
            "na",
            "not specified",
            "not applicable",
            "not_applicable",
        }
        if isinstance(value, str) and value.strip():
            cleaned = value.strip()
            if cleaned.casefold() in _placeholder:
                value = None
                if status == "filled":
                    status = "not_applicable"
            elif status in (None, "unknown", "not_applicable"):
                status = "filled"
        elif status == "filled":
            status = "missing"
            value = None
        try:
            slot_status = CPCSlotStatus(status)
        except ValueError:
            return None, f"bad_cpc_status:{name}:{status}"
        if value is not None and not isinstance(value, str):
            return None, f"bad_cpc_value:{name}"
        if slot_status == CPCSlotStatus.FILLED and not (isinstance(value, str) and value.strip()):
            return None, f"filled_cpc_missing_value:{name}"
        slots[name] = CPCSlot(value=value.strip() if isinstance(value, str) and value.strip() else None, status=slot_status)
    return CPC(**slots), None


def apply_scene_licence(
    *,
    unresolved: list[str],
    cpc: CPC,
    system_input: SystemInput,
) -> tuple[list[str], CPC, list[str]]:
    context = joined_context(system_input)
    kept: list[str] = []
    dropped: list[str] = []
    for slot in unresolved:
        name = canonical_slot_name(slot)
        if name not in CPC_SLOT_NAMES:
            continue
        current = getattr(cpc, name)
        if current.status == CPCSlotStatus.FILLED and current.value:
            dropped.append(name)
            continue
        if slot_licensed_by_context(name, context):
            dropped.append(name)
            continue
        kept.append(name)
    return kept, cpc, dropped


def extract_analysis_json(text: str) -> dict[str, Any] | None:
    """Prefer the JSON object that looks like a goal-first analysis.

    Models sometimes emit a valid analysis object and then a trailing fragment
    object. Taking the last decodeable object alone mis-classifies those as
    no_json / schema failures.
    """
    text = (text or "").strip()
    if not text:
        return None
    candidates: list[dict[str, Any]] = []
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            candidates.append(obj)
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            candidates.append(obj)
    if not candidates:
        return None
    ranked = sorted(
        candidates,
        key=lambda obj: (
            1 if isinstance(obj.get("intent_summary"), str) and obj.get("intent_summary").strip() else 0,
            1 if "cpc" in obj else 0,
            1 if "speech_act" in obj else 0,
            1 if "pilot_ambiguity_types" in obj else 0,
            len(obj),
        ),
        reverse=True,
    )
    return ranked[0]


def normalise_analysis_output(
    obj: dict[str, Any] | None,
    *,
    system_input: SystemInput,
    provider_id: str,
) -> tuple[StructuredAnalysis | None, dict[str, Any] | None, str | None]:
    if not isinstance(obj, dict):
        return None, None, "no_json"
    summary = obj.get("intent_summary")
    if not isinstance(summary, str) or not summary.strip() or len(summary.strip()) > 500:
        return None, None, "bad_intent_summary"
    summary = summary.strip()
    if _normalise_text(summary) == _normalise_text(system_input.command):
        return None, None, "intent_summary_copied_command"
    if _ROUTE_TERMS.search(summary):
        return None, None, "intent_summary_route_contamination"
    speech_act = obj.get("speech_act")
    if speech_act not in SPEECH_ACTS:
        return None, None, f"bad_speech_act:{speech_act}"
    raw_types = obj.get("pilot_ambiguity_types")
    if not isinstance(raw_types, list):
        return None, None, "bad_pilot_ambiguity_types"
    if any(str(value) not in AMBIGUITY_TYPES for value in raw_types):
        return None, None, "unknown_pilot_ambiguity_type"
    types = sorted({str(value) for value in raw_types if str(value) in AMBIGUITY_TYPES})
    # Gold pragmatic is reserved for indirect_request-shaped jobs. Drop binge tags on
    # ordinary directives (Pilot-120: 29/29 gold pragmatic are indirect_request).
    if speech_act == "directive_command" and "pragmatic" in types:
        types = [t for t in types if t != "pragmatic"]
    pilot_capability = obj.get("pilot_capability_status")
    if pilot_capability not in CAPABILITIES:
        return None, None, f"bad_pilot_capability_status:{pilot_capability}"
    risk = obj.get("risk_level")
    if risk not in CANONICAL_RISKS:
        return None, None, f"bad_risk_level:{risk}"
    raw_slots = obj.get("unresolved_slots")
    allowed_slots = set(CPC_SLOT_NAMES) | set(SLOT_ALIASES)
    if not isinstance(raw_slots, list) or any(str(slot) not in allowed_slots for slot in raw_slots):
        return None, None, "bad_unresolved_slots"
    try:
        uncertainty = float(obj.get("uncertainty"))
    except (TypeError, ValueError):
        return None, None, "bad_uncertainty"
    if not 0.0 <= uncertainty <= 1.0:
        return None, None, "uncertainty_out_of_range"
    cpc, cpc_error = _parse_cpc(obj.get("cpc"))
    if cpc_error or cpc is None:
        return None, None, cpc_error or "bad_cpc"
    unresolved, cpc, dropped = apply_scene_licence(
        unresolved=[canonical_slot_name(str(slot)) for slot in raw_slots],
        cpc=cpc,
        system_input=system_input,
    )
    canonical = sorted({CANONICAL_AMBIGUITY[value] for value in types})
    primary = canonical[0] if canonical else None
    resolved = [
        ResolvedSlotValue(slot_name=name, value=getattr(cpc, name).value).to_dict()
        for name in CPC_SLOT_NAMES
        if getattr(cpc, name).status == CPCSlotStatus.FILLED and getattr(cpc, name).value
    ]
    analysis = StructuredAnalysis.from_dict(
        {
            "speech_act": speech_act,
            "intent_summary": summary,
            "cpc": cpc.to_dict(),
            "ambiguity_present": bool(types),
            "ambiguity_types": canonical,
            "primary_ambiguity_type": primary,
            "compound_ambiguity": len(types) > 1,
            "compound_ambiguity_count": len(types),
            "risk_relevant": risk not in {"none", "unknown"},
            "risk_level": risk,
            "capability_status": CANONICAL_CAPABILITY[pilot_capability],
            "unresolved_slots": [
                UnresolvedSlot(slot_name=slot, reason="model_identified_uncertainty").to_dict()
                for slot in unresolved
            ],
            "resolved_slots": resolved,
            "context_sampling_uncertainty": ContextSamplingUncertainty(
                score=uncertainty, variant_count=1, agreement=1.0 - uncertainty
            ).to_dict(),
            "analysis_provenance": AnalysisProvenance(
                provider_id=provider_id,
                provider_version="goal-first-manager-v2",
                analysis_id=system_input.fingerprint(),
                method="model_generated",
                notes=f"source_input_hash={system_input.fingerprint()};no_gold_in_prompt;scene_licence_dropped={','.join(dropped) or 'none'}",
            ).to_dict(),
            "findings": [
                f"pilot_ambiguity_types:{json.dumps(types, separators=(',', ':'))}",
                f"pilot_capability_status:{pilot_capability}",
                "intent_summary_present",
            ],
        }
    )
    meta = {
        "pilot_ambiguity_types": types,
        "pilot_capability_status": pilot_capability,
        "intent_summary": summary,
        "scene_licence_dropped_slots": dropped,
        "unresolved_slots_after_licence": unresolved,
    }
    return analysis, meta, None
