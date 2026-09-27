#!/usr/bin/env python3
"""Shared helpers for capability LLM judge + ambiguity debate packs (2026-09-18).

Reuse frozen intent_summary / parsed.analysis from an existing GF-v2 prediction
file. Only capability (and later ambiguity) fields are rewritten; intent is not
re-emitted.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from ambiguity_manager.systems.contracts import StructuredAnalysis
from ambiguity_manager.systems.goal_first_analysis_v2 import (
    AMBIGUITY_TYPES,
    CANONICAL_CAPABILITY,
    CAPABILITIES,
)
from ambiguity_manager.systems.routing import DeterministicRouter
from ambiguity_manager.systems.variants import DegreeBasedRouterSystem

CAPABILITY_SET = frozenset(CAPABILITIES)
AMBIGUITY_SET = frozenset(AMBIGUITY_TYPES)
ROUTE_SET = frozenset(
    {"execute", "clarify", "refuse", "silently_resolve", "face_preserving_rejection"}
)

_JSON_OBJECT = re.compile(r"\{[\s\S]*\}")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        if "record_id" not in item:
            raise ValueError(f"missing_record_id:{path}:{number}")
        rows.append(item)
    return rows


def load_jsonl_by_id(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in load_jsonl(path):
        rid = str(item["record_id"])
        if rid in rows:
            raise ValueError(f"duplicate_record_id:{path}:{rid}")
        rows[rid] = item
    return rows


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def strip_think_blocks(text: str) -> str:
    """Drop Qwen3 <think>…</think> (and truncated open think) before JSON parse."""
    if not text:
        return ""
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    # Truncated think with no close tag: keep only text after last </think> if any,
    # else drop from <think> onward when no JSON brace remains after it.
    if "<think>" in cleaned.lower():
        lower = cleaned.lower()
        idx = lower.rfind("<think>")
        after = cleaned[idx + len("<think>") :]
        if "{" in after:
            cleaned = after[after.find("{") :]
        else:
            cleaned = cleaned[:idx]
    return cleaned.strip()


def extract_json_object(text: str) -> dict[str, Any] | None:
    if not text or not text.strip():
        return None
    stripped = strip_think_blocks(text)
    if not stripped:
        return None
    try:
        obj = json.loads(stripped)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    match = _JSON_OBJECT.search(stripped)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def norm_route(value: str | None) -> str:
    text = (value or "").strip()
    if text in {"face_preserving_rejection", "reject", "refuse", "rejection"}:
        return "refuse"
    if text in {"clarify", "clarification"}:
        return "clarify"
    if text in {"execute", "act"}:
        return "execute"
    if text in {"silently_resolve"}:
        return "silently_resolve"
    return text


def analysis_dict_from_pred(pred: dict[str, Any]) -> dict[str, Any] | None:
    raw = (pred.get("parsed") or {}).get("analysis")
    if not isinstance(raw, dict) or not raw:
        return None
    return dict(raw)


def intent_from_pred(pred: dict[str, Any]) -> str:
    intent = str(pred.get("intent_summary") or "").strip()
    if intent:
        return intent
    return str(
        ((pred.get("parsed") or {}).get("analysis") or {}).get("intent_summary") or ""
    ).strip()


def patch_capability_in_analysis(
    analysis: dict[str, Any], capability_label: str
) -> dict[str, Any]:
    label = str(capability_label).strip()
    if label not in CAPABILITY_SET:
        raise ValueError(f"bad_capability_label:{label}")
    findings = [
        f
        for f in list(analysis.get("findings") or [])
        if not str(f).startswith("pilot_capability_status:")
    ]
    findings.append(f"pilot_capability_status:{label}")
    out = dict(analysis)
    out["findings"] = findings
    out["capability_status"] = CANONICAL_CAPABILITY[label]
    return out


def analysis_from_dict(analysis: dict[str, Any]) -> StructuredAnalysis:
    return StructuredAnalysis.from_dict(analysis)


def format_context_block(source: dict[str, Any]) -> str:
    history = source.get("dialogue_history") or []
    hist = "\n".join(f"- {item}" for item in history) if history else "(none)"
    scene = source.get("scene_context")
    scene_txt = json.dumps(scene, ensure_ascii=False) if scene is not None else "(none)"
    cap_ctx = source.get("capability_context")
    cap_txt = json.dumps(cap_ctx, ensure_ascii=False) if cap_ctx is not None else "(none)"
    return (
        f"record_id: {source.get('record_id')}\n"
        f"command: {source.get('command')}\n"
        f"dialogue_history:\n{hist}\n"
        f"scene_context: {scene_txt}\n"
        f"capability_context: {cap_txt}\n"
    )


def build_capability_judge_prompt(
    source: dict[str, Any], *, intent_summary: str, prior_capability: str | None
) -> str:
    labels = ", ".join(CAPABILITIES)
    prior = prior_capability or "(missing)"
    return (
        "You are a capability judge for a household/care robot manager.\n"
        "Decide whether the robot can legally and safely perform the job described "
        "by intent_summary, given capability_context and scene.\n"
        "Do NOT rewrite the intent. Do NOT choose a route.\n"
        f"Allowed capability labels (pick exactly one): {labels}\n"
        "Definitions:\n"
        "- capable: robot can do this under current context\n"
        "- conditionally_capable: can do it if a soft condition is met\n"
        "- incapable: physically/operationally cannot\n"
        "- unauthorized: lacks authority / policy forbids without being unsafe\n"
        "- unsafe: would create unacceptable harm risk\n"
        "Prefer capable over unauthorized when capability_context clearly licences the action.\n"
        "Do not write chain-of-thought. First character of your reply must be '{'.\n"
        "Return ONLY a JSON object with keys: capability_status, confidence (0-1), reason.\n\n"
        f"{format_context_block(source)}"
        f"intent_summary (frozen): {intent_summary}\n"
        f"prior_emit_capability_hint: {prior}\n"
    )


def build_debate_prompt(
    role: str,
    source: dict[str, Any],
    *,
    intent_summary: str,
    prior_ambiguity: list[str] | None,
    other_argument: str | None = None,
) -> str:
    labels = ", ".join(AMBIGUITY_TYPES)
    prior = json.dumps(prior_ambiguity or [], ensure_ascii=False)
    stance = {
        "debater_a": (
            "You are Debater A. Argue for the most complete ambiguity set that is "
            "actually present. Prefer recall when unsure, but only use Pilot-17 labels."
        ),
        "debater_b": (
            "You are Debater B. Argue for a minimal ambiguity set. Prefer precision; "
            "drop types that are not clearly licensed by the utterance/context."
        ),
        "adjudicator": (
            "You are the Adjudicator. Read both debaters. Choose the final "
            "pilot_ambiguity_types set and a suggested_route with written reasons. "
            "suggested_route must be exactly one of: execute, clarify, refuse, silently_resolve."
        ),
    }[role]
    other = ""
    if other_argument:
        other = f"\nOther debater / prior arguments:\n{other_argument}\n"
    example = (
        '{"pilot_ambiguity_types":["temporal_reference"],'
        '"suggested_route":"clarify","confidence":0.7,'
        '"reason":"time slot underspecified"}'
    )
    return (
        f"{stance}\n"
        "Frozen intent_summary must be treated as given; do not rewrite the job.\n"
        f"Allowed pilot_ambiguity_types labels ONLY: {labels}\n"
        "Do not write chain-of-thought. First character of your reply must be '{'.\n"
        "Return ONLY a JSON object. Exact keys required:\n"
        "  pilot_ambiguity_types: array of allowed labels (may be empty)\n"
        "  suggested_route: exactly one of execute|clarify|refuse|silently_resolve "
        "(never paraphrase the job here)\n"
        "  confidence: number 0-1\n"
        "  reason: short string\n"
        "For adjudicator also include: accept_debater (A|B|blend), dissent_notes.\n"
        f"Example: {example}\n\n"
        f"{format_context_block(source)}"
        f"intent_summary (frozen): {intent_summary}\n"
        f"prior_emit_pilot_ambiguity_types: {prior}\n"
        f"{other}"
    )


def normalise_capability_obj(obj: dict[str, Any] | None) -> tuple[str | None, dict[str, Any]]:
    if not obj:
        return None, {"error": "empty_json"}
    label = str(obj.get("capability_status") or "").strip()
    if label not in CAPABILITY_SET:
        return None, {"error": "bad_capability_status", "raw": obj}
    conf = obj.get("confidence")
    try:
        confidence = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        confidence = None
    reason = str(obj.get("reason") or "").strip()
    return label, {"capability_status": label, "confidence": confidence, "reason": reason}


def _extract_ambiguity_types(obj: dict[str, Any]) -> list[Any] | None:
    for key in (
        "pilot_ambiguity_types",
        "pilot_ambiguuity_types",  # common model typo
        "pilot_ambiguities",
        "ambiguity_types",
        "ambiguities",
        "types",
    ):
        raw = obj.get(key)
        if isinstance(raw, list):
            return raw
    # Nested adjudicator-style blobs
    for nest_key in ("adjudicator", "final", "decision"):
        nested = obj.get(nest_key)
        if isinstance(nested, dict):
            found = _extract_ambiguity_types(nested)
            if found is not None:
                return found
    return None


def _extract_suggested_route(obj: dict[str, Any]) -> str | None:
    for key in ("suggested_route", "route", "recommended_strategy", "terminal_strategy"):
        if key in obj and obj.get(key) is not None:
            return str(obj.get(key))
    for nest_key in ("adjudicator", "final", "decision"):
        nested = obj.get(nest_key)
        if isinstance(nested, dict):
            found = _extract_suggested_route(nested)
            if found is not None:
                return found
    return None


def _coerce_route(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    route = norm_route(text)
    if route == "face_preserving_rejection":
        route = "refuse"
    if route in {"execute", "clarify", "refuse", "silently_resolve"}:
        return route
    # Free-text paraphrase: look for an explicit route token.
    lower = text.lower()
    for token in ("silently_resolve", "face_preserving_rejection", "execute", "clarify", "refuse"):
        if re.search(rf"\b{token}\b", lower):
            return "refuse" if token == "face_preserving_rejection" else token
    return None


def normalise_debate_obj(obj: dict[str, Any] | None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not obj:
        return None, {"error": "empty_json"}
    raw_types = _extract_ambiguity_types(obj)
    if raw_types is None:
        return None, {"error": "bad_pilot_ambiguity_types", "raw": obj}
    dropped = [str(v) for v in raw_types if str(v) not in AMBIGUITY_SET]
    types = sorted({str(v) for v in raw_types if str(v) in AMBIGUITY_SET})
    route = _coerce_route(_extract_suggested_route(obj))
    route_missing = route is None
    if route_missing:
        # Keep types even when the model paraphrased the job into suggested_route.
        route = None
    try:
        confidence = float(obj["confidence"]) if obj.get("confidence") is not None else None
    except (TypeError, ValueError):
        confidence = None
    out = {
        "pilot_ambiguity_types": types,
        "suggested_route": route,
        "confidence": confidence,
        "reason": str(obj.get("reason") or "").strip(),
        "accept_debater": str(obj.get("accept_debater") or "").strip() or None,
        "dissent_notes": str(obj.get("dissent_notes") or "").strip() or None,
        "dropped_unknown_types": dropped or None,
        "route_missing": route_missing,
    }
    # Require a valid route for a fully successful parse; callers may still use types.
    if route_missing:
        return out, {
            "error": "bad_suggested_route",
            "partial": True,
            "kept_types": types,
            "dropped_types": dropped,
        }
    return out, {"ok": True, "dropped_unknown_types": dropped}


def prior_capability_from_pred(pred: dict[str, Any]) -> str | None:
    analysis = (pred.get("parsed") or {}).get("analysis") or {}
    for finding in analysis.get("findings") or []:
        text = str(finding)
        if text.startswith("pilot_capability_status:"):
            return text.split(":", 1)[1].strip()
    top = pred.get("capability_status")
    return str(top) if top else None


def prior_ambiguity_from_pred(pred: dict[str, Any]) -> list[str]:
    analysis = (pred.get("parsed") or {}).get("analysis") or {}
    for finding in analysis.get("findings") or []:
        text = str(finding)
        if text.startswith("pilot_ambiguity_types:"):
            try:
                raw = json.loads(text.split(":", 1)[1])
            except json.JSONDecodeError:
                return []
            if isinstance(raw, list):
                return [str(v) for v in raw if str(v) in AMBIGUITY_SET]
    types = pred.get("ambiguity_types") or analysis.get("ambiguity_types") or []
    if isinstance(types, list):
        return [str(v) for v in types]
    return []


def route_from_analysis(analysis: StructuredAnalysis) -> dict[str, str]:
    """CPU re-route only; does not call any LLM."""
    from ambiguity_manager.systems.contracts import SystemInput
    import copy

    gf = DeterministicRouter(policy="goal_first_v2").route(analysis)
    timid = DeterministicRouter().route(analysis)  # t39_conservative
    dummy = SystemInput(
        record_id=str(getattr(analysis, "record_id", None) or "tmp"),
        command="tmp",
        dialogue_history=(),
        scene_context=None,
        capability_context=None,
        protected_data=False,
    )
    degree_out = DegreeBasedRouterSystem().run(dummy, cached_analysis=copy.deepcopy(analysis))
    degree_route = degree_out.recommended_strategy
    return {
        "goal_first_manager_v2": norm_route(
            gf.recommended_strategy.value
            if hasattr(gf.recommended_strategy, "value")
            else str(gf.recommended_strategy)
        ),
        "rich_conservative_manager_v2": norm_route(
            timid.recommended_strategy.value
            if hasattr(timid.recommended_strategy, "value")
            else str(timid.recommended_strategy)
        ),
        "degree_based_router_v2": norm_route(
            degree_route.value if hasattr(degree_route, "value") else str(degree_route)
        ),
    }


def slice_stats(rows: list[dict[str, Any]], pred_key: str) -> dict[str, Any]:
    n = len(rows)
    correct = sum(1 for r in rows if r[pred_key] == r["gold_route"])
    gold_exec = [r for r in rows if r["gold_route"] == "execute"]
    gold_ref = [r for r in rows if r["gold_route"] == "refuse"]
    preds = [r[pred_key] for r in rows]
    conf: dict[str, dict[str, int]] = {}
    for r in rows:
        conf.setdefault(r["gold_route"], {})
        conf[r["gold_route"]][r[pred_key]] = conf[r["gold_route"]].get(r[pred_key], 0) + 1
    return {
        "n": n,
        "n_correct": correct,
        "accuracy": (correct / n) if n else 0.0,
        "pred_counts": dict(Counter(preds)),
        "execute_recall_gold_exec": (
            sum(1 for r in gold_exec if r[pred_key] == "execute") / len(gold_exec)
            if gold_exec
            else None
        ),
        "refuse_precision": (
            sum(1 for r in rows if r[pred_key] == "refuse" and r["gold_route"] == "refuse")
            / max(1, sum(1 for r in rows if r[pred_key] == "refuse"))
        ),
        "false_refuse_on_gold_execute": sum(
            1 for r in gold_exec if r[pred_key] == "refuse"
        ),
        "confusion_gold_to_pred": conf,
        "n_gold_execute": len(gold_exec),
        "n_gold_refuse": len(gold_ref),
    }
