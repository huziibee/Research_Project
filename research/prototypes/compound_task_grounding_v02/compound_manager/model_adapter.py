"""Raw utterance -> model-ready TaskSpec prompt; inference is injected externally.

This is deliberately NOT an LLM inference backend. The caller may feed the
prompt to ChatGPT, Qwen, or another structured-output model, parse the JSON,
then pass the result to the deterministic `resolve()` function.
"""
from __future__ import annotations
import json
from typing import Any
from .engine import check_spec, resolve

PROMPT_VERSION = "compound_task_spec_v0.1"
SOURCE_ALLOWLIST = ("command", "scene_context", "dialogue_history")


def build_model_prompt(source: dict) -> str:
    """Never expose gold labels, prior predictions, or route outputs."""
    data = {name: source.get(name, [] if name == "dialogue_history" else "") for name in SOURCE_ALLOWLIST}
    if not data["command"]:
        raise ValueError("missing_command")
    return ("You are a task-graph parser. Transform the INPUT_JSON into a single strict JSON TaskSpec. "
            "Do not classify safety, capability, permission, refusal, or evaluation labels. "
            "Do NOT guess referents or silently fill missing action-critical details. "
            "First identify all requested actions, negation scope, temporal relations, cross-action coreferences, "
            "conditions and required arguments. Preserve alternative *action graphs* if the command's scope or intent "
            "is ambiguous. Next identify candidate values for each unresolved action-critical variable. "
            "Use scene and dialogue to ground a unique choice only when evidence really distinguishes it; "
            "otherwise leave grounded null. Every variable must have a non-empty domain of potential alternatives; "
            "if domain coverage is not possible, STOP and return an error instead of inventing one. "
            "If a command has a dependent return location or other dependent parameter, encode a $lookup expression "
            "rather than independent guesses. For quantities derived from explicit context, use $add and $mul. "
            "Emit order explicitly using each action's after list. Use literals for context-grounded values. "
            "For ambiguous negation or action scope, use multiple guarded templates keyed by a scope variable. "
            "Record exact supporting text snippets from INPUT_JSON in context_evidence. Do not state the final route; "
            "the downstream deterministic verifier computes action readiness. "
            "Schema guide: required JSON keys are schema_version='0.1', record_id='development_case', "
            "utterance=input command, context_evidence=[verbatim snippets], variables={name:{options:[{value,evidence}]," 
            "question:'...',grounded:<option value or null>}}, lookups={table:{key:value}}, "
            "templates=[{actions:[{id:'A1',op:'PICK',args:{object:{$var:'thing'}},after:[]}, ...]," 
            "guard:{var:'scope',equals:'case1'} OPTIONAL}], fixture_status='model_generated_unvalidated'. "
            "Never use missing/unknown as a filled literal. Numeric quantities should stay numeric. "
            "Give one parseable JSON object and no surrounding prose. The generated candidate set is a proposal, "
            "not proof that all alternatives were discovered.\n"
            f"PROMPT_VERSION={PROMPT_VERSION}\n"
            f"INPUT_JSON={json.dumps(data,ensure_ascii=False,sort_keys=True)}")


def process_model_output(source: dict, output_json: str) -> dict[str,Any]:
    """Parse an externally obtained model output; reject unsupported quotes.

    Exact substring checking is a *minimal* provenance check and does NOT
    establish semantic correctness or candidate completeness.
    """
    obj = json.loads(output_json)
    obj["record_id"] = str(source.get("record_id", "development_case"))
    obj["utterance"] = str(source["command"])
    check_spec(obj)
    source_text = "\n".join(str(source.get(f) or "") for f in SOURCE_ALLOWLIST).casefold()
    for quote in obj.get("context_evidence", []):
        if not isinstance(quote,str) or not quote.strip() or quote.casefold() not in source_text:
            raise ValueError(f"unsupported_context_evidence:{quote}")
    return resolve(obj)