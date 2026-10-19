"""Deterministic compound-task grounding, equivalence checking, and questions.

Consumes a model-authored TaskSpec, not raw natural language. No inference, gold,
robot-capability, authorization, or safety decisions occur in this module.
"""
from __future__ import annotations

import itertools
import json
import re
from collections import defaultdict
from copy import deepcopy
from typing import Any

MAX_CANDIDATES = 4096


def stable(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _eval(expr: Any, binding: dict, spec: dict) -> Any:
    if isinstance(expr, list):
        return [_eval(item, binding, spec) for item in expr]
    if not isinstance(expr, dict):
        return expr
    if len(expr) == 1 and "$var" in expr:
        return binding[expr["$var"]]
    if len(expr) == 1 and "$lookup" in expr:
        lookup = expr["$lookup"]
        key = str(_eval(lookup["key"], binding, spec))
        try:
            return spec["lookups"][lookup["table"]][key]
        except KeyError as e:
            raise ValueError(f"unresolved_lookup:{lookup['table']}:{key}") from e
    if len(expr) == 1 and "$mul" in expr:
        product = 1
        for arg in expr["$mul"]:
            product *= _eval(arg, binding, spec)
        return round(product, 9)
    if len(expr) == 1 and "$add" in expr:
        return round(sum(_eval(arg, binding, spec) for arg in expr["$add"]), 9)
    if any(k.startswith("$") for k in expr):
        raise ValueError(f"unknown_expression:{list(expr)}")
    return {key: _eval(value, binding, spec) for key, value in expr.items()}


def check_spec(spec: dict) -> None:
    """Validate task schema and candidate sources before any readiness verdict."""
    assert spec.get("schema_version") == "0.1", "schema_version"
    assert isinstance(spec.get("record_id"), str), "record_id"
    assert spec.get("utterance"), "utterance"
    assert isinstance(spec.get("context_evidence", []), list), "context_evidence"
    assert isinstance(spec.get("lookups", {}), dict), "lookups"
    variables = spec["variables"]
    assert isinstance(variables, dict), "variables"
    for name, data in variables.items():
        options = data.get("options")
        assert isinstance(options, list) and options, f"empty_domain:{name}"
        values = [opt["value"] for opt in options]
        assert len(set(map(stable, values))) == len(values), f"duplicate_option:{name}"
        assert all(isinstance(opt.get("evidence"), str) and opt["evidence"] for opt in options), f"missing_evidence:{name}"
        if data.get("grounded") is not None:
            assert data["grounded"] in values, f"grounded_not_in_domain:{name}"
        else:
            assert data.get("question"), f"missing_question:{name}"
    assert isinstance(spec.get("templates"), list) and spec["templates"], "templates"
    for template in spec["templates"]:
        guard = template.get("guard")
        if guard is not None:
            assert guard["var"] in variables, "unknown_guard_var"
            assert guard["equals"] in [o["value"] for o in variables[guard["var"]]["options"]], "unknown_guard_value"
        actions = template.get("actions")
        assert isinstance(actions, list) and actions, "empty_action_graph"
        ids = [a["id"] for a in actions]
        assert len(ids) == len(set(ids)), "duplicate_action_id"
        previous = set()
        for action in actions:
            assert isinstance(action.get("op"), str) and action["op"], "missing_op"
            assert isinstance(action.get("args"), dict), "args"
            assert all(dep in previous for dep in action.get("after", [])), "invalid_action_order"
            previous.add(action["id"])


def apply_answer(spec: dict, variable: str, value: Any) -> dict:
    """Return a new immutable-style state after one validated user answer."""
    if variable not in spec["variables"]:
        raise ValueError(f"unknown_variable:{variable}")
    options = [o["value"] for o in spec["variables"][variable]["options"]]
    if value not in options:
        raise ValueError(f"invalid_answer:{variable}={value};choose_from={options}")
    if spec["variables"][variable].get("grounded") is not None and spec["variables"][variable]["grounded"] != value:
        raise ValueError(f"contradicts_grounded_context:{variable}")
    updated = deepcopy(spec)
    updated["variables"][variable]["grounded"] = value
    updated.setdefault("answer_history", []).append({"variable": variable, "value": value, "source": "user_answer"})
    return updated


def _instantiate(spec: dict, binding: dict) -> dict:
    compatible = [t for t in spec["templates"] if t.get("guard") is None or binding[t["guard"]["var"]] == t["guard"]["equals"]]
    if len(compatible) != 1:
        raise ValueError(f"template_not_unique:{len(compatible)}")
    template = compatible[0]
    actions = []
    for a in template["actions"]:
        action = {"id": a["id"], "op": a["op"], "args": _eval(a["args"], binding, spec), "after": a.get("after", [])}
        actions.append(action)
    return {"actions": actions}


def _candidate_bindings(spec: dict) -> list[dict]:
    domains = []
    for var, desc in spec["variables"].items():
        resolved = desc.get("grounded")
        values = [resolved] if resolved is not None else [opt["value"] for opt in desc["options"]]
        domains.append((var, values))
    count = 1
    for _, values in domains:
        count *= len(values)
        if count > MAX_CANDIDATES:
            raise ValueError("candidate_limit_exceeded:abstain_instead_of_guess")
    names = [d[0] for d in domains]
    return [dict(zip(names, options)) for options in itertools.product(*(d[1] for d in domains))]


def _partition_score(variable: str, assignments: list[dict], signatures: list[str]) -> tuple:
    """Expected number of distinct tasks after answer, with uniform rows.

    Uniform over assignments is a *heuristic*, not a calibrated user prior.
    """
    groups = defaultdict(set)
    counts = defaultdict(int)
    for binding, signature in zip(assignments, signatures):
        groups[stable(binding[variable])].add(signature)
        counts[stable(binding[variable])] += 1
    n = len(assignments)
    expected = sum(counts[key] / n * len(value) for key, value in groups.items())
    return (expected, max(map(len, groups.values())), variable)


def resolve(spec: dict) -> dict:
    check_spec(spec)
    try:
        assignments = _candidate_bindings(spec)
        tasks = [_instantiate(spec, binding) for binding in assignments]
    except ValueError as e:
        return {"record_id": spec["record_id"], "status": "needs_context_repair", "reason": str(e), "action_ready": False}

    signatures = [stable(t) for t in tasks]
    unique: dict[str, dict] = {}
    for sig, task in zip(signatures, tasks):
        unique[sig] = task
    if len(unique) == 1:
        selected = next(iter(unique.values()))
        return {
            "record_id": spec["record_id"], "status": "action_ready", "action_ready": True,
            "complete_task": selected, "candidate_assignments": len(assignments),
            "distinct_tasks": 1,
            "grounded_bindings": {name: desc.get("grounded") for name, desc in spec["variables"].items()},
            "answer_history": spec.get("answer_history", []),
            "scope": "textual_task_specification_only_not_physical_execution",
        }
    unresolved = [name for name, desc in spec["variables"].items() if desc.get("grounded") is None]
    if not unresolved:
        return {"record_id":spec["record_id"], "status":"needs_context_repair", "reason":"different_tasks_but_no_unresolved_variables", "action_ready":False}
    scored = sorted([(_partition_score(name, assignments, signatures), name) for name in unresolved])
    chosen = scored[0][1]
    return {
        "record_id": spec["record_id"], "status": "needs_clarification", "action_ready": False,
        "candidate_assignments": len(assignments), "distinct_tasks": len(unique),
        "blocking_variables": unresolved, "question_target": chosen,
        "question": spec["variables"][chosen]["question"],
        "answer_options": [o["value"] for o in spec["variables"][chosen]["options"]],
        "candidate_tasks": list(unique.values())[:10],
        "question_selection": "uniform_candidate_partition_heuristic_not_calibrated",
    }