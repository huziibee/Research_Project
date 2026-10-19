"""Stage-by-stage compound ambiguity pipeline with conservative verification.

A provider generates a candidate TaskSpec; this module does not claim to be a
language model. The deterministic reasoning is valid only over enumerated,
evidence-backed alternatives. It deliberately excludes capability/risk gating.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .engine import apply_answer, check_spec, resolve, stable
from .model_adapter import build_model_prompt

SOURCE_FIELDS = ("command", "scene_context", "dialogue_history")


class LanguageModel(Protocol):
    def generate(self, prompt: str, source: dict[str, Any]) -> str: ...


class TaskParseError(ValueError):
    pass


def _source_text(source: dict[str, Any]) -> str:
    return "\n".join(
        "\n".join(str(i) for i in source.get(key, []))
        if isinstance(source.get(key), list) else str(source.get(key, ""))
        for key in SOURCE_FIELDS
    )


def _evidence_audit(source: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """Only exact-quote evidence is verifiable. No semantic validity claim."""
    text = _source_text(source).casefold()
    unsupported: list[str] = []
    for evidence in spec.get("context_evidence", []):
        if not isinstance(evidence, str) or not evidence.strip() or evidence.casefold() not in text:
            unsupported.append(f"context:{evidence!r}")
    for name, item in spec["variables"].items():
        for option in item["options"]:
            quote = option.get("evidence", "")
            if not isinstance(quote, str) or not quote.strip() or quote.casefold() not in text:
                unsupported.append(f"option:{name}:{quote!r}")
    return {
        "quotes_verified": not unsupported,
        "unsupported_quotes": unsupported,
        "candidate_coverage_verified": False,
        "note": "Verbatim quote presence is not independent semantic or candidate-recall validation.",
    }


def _referenced_variables(value: Any) -> set[str]:
    if isinstance(value, list):
        return set().union(*(_referenced_variables(i) for i in value)) if value else set()
    if isinstance(value, dict):
        if set(value) == {"$var"}:
            return {str(value["$var"])}
        found: set[str] = set()
        for sub in value.values():
            found.update(_referenced_variables(sub))
        return found
    return set()


def dependency_analysis(spec: dict[str, Any]) -> dict[str, Any]:
    """Inspect cross-action variable reuse and dependent lookups."""
    used_by: dict[str, set[str]] = {key: set() for key in spec["variables"]}
    lookups: list[dict[str, str]] = []
    for template in spec["templates"]:
        for action in template["actions"]:
            for variable in _referenced_variables(action["args"]):
                used_by.setdefault(variable, set()).add(action["id"])
            def walk(v: Any) -> None:
                if isinstance(v, dict):
                    if "$lookup" in v:
                        item = v["$lookup"]
                        lookups.append({"table": str(item["table"]), "depends_on": ",".join(sorted(_referenced_variables(item["key"])))})
                    for z in v.values():
                        walk(z)
                elif isinstance(v, list):
                    for z in v:
                        walk(z)
            walk(action["args"])
    return {
        "variable_count": len(spec["variables"]),
        "unresolved_count": sum(d.get("grounded") is None for d in spec["variables"].values()),
        "shared_across_actions": {v: sorted(ids) for v, ids in used_by.items() if len(ids) > 1},
        "dependent_lookups": lookups,
        "alternative_action_graphs": len(spec["templates"]),
        "classification": ("dependent_compound" if lookups or any(len(ids)>1 for ids in used_by.values()) or len(spec["templates"])>1
            else "multiple_independent" if sum(d.get("grounded") is None for d in spec["variables"].values()) >= 2
            else "single_or_resolved"),
    }


def validate_spec_expressions(spec: dict[str, Any]) -> None:
    """Prevent unknown variables, undeclared lookup tables and action cycles."""
    check_spec(spec)
    names = set(spec["variables"])
    for template in spec["templates"]:
        guard = template.get("guard")
        if guard and guard["var"] not in names:
            raise TaskParseError("unknown_guard_variable")
        for action in template["actions"]:
            if _referenced_variables(action["args"]) - names:
                raise TaskParseError("unknown_variable_reference")
            def walk(v: Any) -> None:
                if isinstance(v, dict):
                    if "$lookup" in v:
                        lookup = v["$lookup"]
                        if lookup.get("table") not in spec.get("lookups", {}):
                            raise TaskParseError("unknown_lookup_table")
                    for part in v.values(): walk(part)
                elif isinstance(v, list):
                    for part in v: walk(part)
            walk(action["args"])


def parse_task_spec(source: dict[str, Any], response: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """No gold fields or model routes are accepted into semantic output."""
    try:
        obj = json.loads(response)
    except (ValueError, TypeError) as e:
        raise TaskParseError("invalid_json") from e
    if not isinstance(obj, dict):
        raise TaskParseError("json_object_required")
    if obj.get("utterance") not in (None, source.get("command")):
        raise TaskParseError("utterance_mismatch")
    obj["record_id"] = str(source.get("record_id", "unlabelled"))
    obj["utterance"] = str(source["command"])
    obj.setdefault("context_evidence", [])
    obj.setdefault("lookups", {})
    if any(name in obj for name in ("gold_route", "terminal_strategy", "risk_level", "capability_status")):
        raise TaskParseError("route_or_policy_field_in_semantics")
    try:
        validate_spec_expressions(obj)
    except (AssertionError, KeyError, TypeError, ValueError) as e:
        raise TaskParseError(f"invalid_task_spec:{e}") from e
    return obj, _evidence_audit(source, obj)


def run_first_turn(source: dict[str, Any], model: LanguageModel, *, strict_evidence: bool = True) -> dict[str, Any]:
    """One interpretation and one deterministic grounding decision."""
    try:
        raw = model.generate(build_model_prompt(source), source)
        spec, audit = parse_task_spec(source, raw)
        verdict = resolve(spec)
        deps = dependency_analysis(spec)
        if strict_evidence and not audit["quotes_verified"]:
            verdict = {"record_id": spec["record_id"], "status": "needs_context_repair", "action_ready": False,
                       "reason": "unsupported_source_evidence"}
        return {"record_id": source.get("record_id"), "status": verdict["status"],
                "spec": spec, "verdict": verdict, "audit": audit, "dependencies": deps,
                "inference_source": "injected_language_model", "ready_with_full_coverage_verified": False}
    except (TaskParseError, AssertionError, TypeError, ValueError, KeyError) as e:
        return {"record_id": source.get("record_id"), "status": "parse_failed",
                "verdict": {"status": "needs_context_repair", "action_ready": False, "reason": str(e)},
                "inference_source": "injected_language_model", "ready_with_full_coverage_verified": False}


def _parse_answer(answer: str, variable: str, options: list[Any]) -> Any:
    """Exact normalized option matching only; do not guess from ambiguous prose."""
    candidate = answer.strip().casefold()
    for val in options:
        if candidate == str(val).casefold():
            return val
    prefix = variable.casefold() + "="
    if candidate.startswith(prefix):
        return _parse_answer(candidate[len(prefix):], variable, options)
    raise ValueError("ambiguous_or_unrecognized_answer")


def answer_turn(state: dict[str, Any], answer: str) -> dict[str, Any]:
    """Update *only* the asked variable, then re-ground the full graph."""
    if state["verdict"]["status"] != "needs_clarification":
        raise ValueError("no_pending_question")
    variable = state["verdict"]["question_target"]
    value = _parse_answer(answer, variable, state["verdict"]["answer_options"])
    out = deepcopy(state)
    out["spec"] = apply_answer(out["spec"], variable, value)
    out["verdict"] = resolve(out["spec"])
    out["status"] = out["verdict"]["status"]
    out["dependencies"] = dependency_analysis(out["spec"])
    return out


def run_dialogue(source: dict[str, Any], model: LanguageModel, answers: list[str], *, max_questions: int = 5,
                 strict_evidence: bool = True) -> dict[str, Any]:
    if max_questions < 0 or max_questions > 5:
        raise ValueError("max_questions_out_of_range")
    state = run_first_turn(source, model, strict_evidence=strict_evidence)
    turns = 0
    for answer in answers[:max_questions]:
        if state["verdict"]["status"] != "needs_clarification":
            break
        try:
            state = answer_turn(state, answer)
            turns += 1
        except ValueError as error:
            state["answer_error"] = str(error)
            break
    state["turns_used"] = turns
    if state["verdict"]["status"] == "needs_clarification" and turns >= max_questions:
        state["termination"] = "depth_cap"
    else:
        state["termination"] = state["verdict"]["status"]
    return state


@dataclass
class FixtureModel:
    """Deterministic fake backend for unit tests and transparent demonstrations."""
    by_record_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    def generate(self, prompt: str, source: dict[str, Any]) -> str:
        rid = source["record_id"]
        if rid not in self.by_record_id:
            raise TaskParseError(f"no_structured_fixture:{rid}")
        return json.dumps(self.by_record_id[rid], ensure_ascii=False)