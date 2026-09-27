#!/usr/bin/env python3
"""Extract frozen T39 model reasoning and cluster why routes happened.

Does not modify T39 predictions. Thinking text is already in raw_output;
this makes it queryable so the traces can drive insights.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRED_DIR = ROOT / "review_bundles" / "pilot120_t39_20260902" / "cluster_outputs" / "R1" / "manager" / "predictions"
GOLD = ROOT / "data" / "annotations" / "pilot_120_v1" / "pilot_120_final_gold.jsonl"
INTENT = ROOT / "pilot120_intent_evaluation_20260902" / "pilot120_intent_evaluation_20260902" / "data" / "intent_gold_references_120.jsonl"
ROWS = ROOT / "outputs" / "pilot120_semantic_intent_judging_20260908" / "final_intent_rows.csv"
GOAL_FIRST = ROOT / "outputs" / "goal_first_manager_v1_counterfactual_20260911.json"
OUT_JSONL = ROOT / "outputs" / "t39_reasoning_ledger_20260911.jsonl"
OUT_JSON = ROOT / "outputs" / "t39_reasoning_clusters_20260911.json"

FULL_SYSTEM = "full_type_risk_aware_manager"
SYSTEMS = (
    "full_type_risk_aware_manager",
    "context_blind_manager",
    "degree_based_router",
)

THINK_RE = re.compile(r"<think>(.*?)</think>", re.S | re.I)
CLOCK_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
TREAT_AS_REQUEST_RE = re.compile(
    r"treat(?: that| this| it)? as (?:a |an )?(?:request|instruction|directive)|not a capability",
    re.I,
)
ASK_INSTEAD_RE = re.compile(
    r"\b(ambiguous|unclear|not (?:completely )?sure|unsure|unresolved|need(?:s)? to (?:ask|clarify)|should (?:ask|clarify))\b",
    re.I,
)
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
    "tool": ("scale", "cart", "tray", "scanner", "printer"),
    "recipient": ("recipient", "nurse", "clerk", "paired"),
    "quantity": ("kg", "kilogram", "below", "limit"),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["record_id"]] = row
    return rows


def extract_think(raw: str) -> dict:
    text = raw or ""
    closed = THINK_RE.search(text)
    if closed:
        think = closed.group(1).strip()
        return {"has_think": True, "think_closed": True, "think_chars": len(think), "think": think}
    lowered = text.lower()
    if "<think>" in lowered:
        start = lowered.find("<think>") + len("<think>")
        think = text[start:].strip()
        return {"has_think": True, "think_closed": False, "think_chars": len(think), "think": think}
    return {"has_think": False, "think_closed": False, "think_chars": 0, "think": ""}


def joined_context(source: dict) -> str:
    dialogue = source.get("dialogue_history") or []
    if isinstance(dialogue, list):
        dialogue_text = " ".join(str(item) for item in dialogue)
    else:
        dialogue_text = str(dialogue)
    return " ".join(
        [
            str(source.get("command") or ""),
            str(source.get("scene_context") or ""),
            dialogue_text,
            str(source.get("capability_context") or ""),
        ]
    )


def slot_licensed_by_context(slot: str, context: str) -> bool:
    text = context.casefold()
    if slot == "time" and CLOCK_RE.search(text):
        return True
    cues = SCENE_SLOT_CUES.get(slot, (slot,))
    return any(cue in text for cue in cues)


def scene_facts_reused_in_think(think: str, context: str) -> list[str]:
    reused = []
    clocks = sorted(set(CLOCK_RE.findall(context)))
    for clock in clocks:
        if clock in think:
            reused.append(clock)
    for token in ("PENDING", "COMPLETE", "MOVE"):
        if token in context.upper() and token.lower() in think.casefold():
            reused.append(token)
    return reused


def cluster_reason(row: dict) -> str:
    gold = row["gold_route"]
    pred = row["predicted_route"]
    think = row.get("think") or ""
    targets = [str(t) for t in row.get("clarification_targets") or []]
    licensed = row.get("asked_slots_licensed_by_context") or []
    if pred == "execute":
        return "executed"
    if pred == "face_preserving_rejection":
        if gold == "face_preserving_rejection":
            return "refused_when_gold_refused"
        return "refused_when_gold_wanted_action_or_ask"
    if pred != "clarify":
        return "other"
    if gold == "clarify":
        return "asked_when_gold_also_wanted_a_question"
    if gold == "face_preserving_rejection":
        return "asked_instead_of_refusing"
    # gold execute, predicted clarify
    if row.get("think_mentions_treat_as_request") and licensed:
        return "knew_it_was_a_request_but_asked_for_scene_slots"
    if licensed:
        return "asked_for_slots_already_licensed_by_scene"
    if row.get("capability_status") in {"conditional", "conditionally_capable"}:
        return "treated_executable_job_as_unverified_condition"
    if any(word in think.casefold() for word in ("capability question", "asking if", "whether it can")):
        return "treated_request_as_capability_question"
    if ASK_INSTEAD_RE.search(think):
        return "named_ambiguity_in_think_then_asked"
    if targets:
        return "clarified_gold_execute_other_slots"
    return "clarified_gold_execute_other"


def main() -> None:
    if OUT_JSONL.exists() or OUT_JSON.exists():
        raise ValueError("output_exists")
    gold = load_jsonl(GOLD)
    intent = load_jsonl(INTENT)
    scored_by_system: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in csv.DictReader(ROWS.open(encoding="utf-8", newline="")):
        scored_by_system[row["system_id"]][row["record_id"]] = row
    goal_first = {}
    if GOAL_FIRST.exists():
        payload = json.loads(GOAL_FIRST.read_text(encoding="utf-8"))
        goal_first = {row["record_id"]: row["predicted_route"] for row in payload.get("rows", [])}

    ledger = []
    hashes = {"gold": sha(GOLD)}
    for system_id in SYSTEMS:
        pred_path = PRED_DIR / f"{system_id}.predictions.jsonl"
        hashes[system_id] = sha(pred_path)
        preds = load_jsonl(pred_path)
        for record_id, pred in preds.items():
            analysis = (pred.get("parsed") or {}).get("analysis") or {}
            runtime = ((pred.get("parsed") or {}).get("runtime_metadata") or {})
            router = runtime.get("router_trace") or {}
            think_info = extract_think(str(pred.get("raw_output") or ""))
            score = scored_by_system[system_id][record_id]
            source = intent[record_id]["source"]
            context = joined_context(source)
            targets = list(analysis.get("clarification_targets") or pred.get("clarification_targets") or [])
            licensed = [slot for slot in targets if slot_licensed_by_context(str(slot), context)]
            think = think_info["think"]
            row = {
                "record_id": record_id,
                "system_id": system_id,
                "command": source["command"],
                "scene_context": source.get("scene_context"),
                "dialogue_history": source.get("dialogue_history") or [],
                "gold_route": gold[record_id]["terminal_strategy"],
                "predicted_route": pred.get("terminal_strategy"),
                "gold_speech_act": score["gold_speech_act"],
                "predicted_speech_act": score["predicted_speech_act"],
                "semantic_goal_correct": score["semantic_goal_correct"] == "True",
                "speech_act_correct": score["speech_act_correct"] == "True",
                "route_correct": score["route_correct"] == "True",
                "clarification_question": analysis.get("clarification_question"),
                "clarification_targets": targets,
                "asked_slots_licensed_by_context": licensed,
                "unresolved_slots": [
                    u.get("slot_name") for u in (analysis.get("unresolved_slots") or []) if isinstance(u, dict)
                ],
                "capability_status": analysis.get("capability_status"),
                "risk_level": analysis.get("risk_level"),
                "matched_rule_id": router.get("matched_rule_id"),
                "intent_summary_frozen": analysis.get("intent_summary"),
                "goal_first_route": goal_first.get(record_id) if system_id == FULL_SYSTEM else None,
                "think_mentions_treat_as_request": bool(TREAT_AS_REQUEST_RE.search(think)),
                "think_reused_scene_facts": scene_facts_reused_in_think(think, context),
                **think_info,
            }
            row["reasoning_cluster"] = cluster_reason(row)
            row["think_excerpt"] = (row["think"][:500] + "…") if len(row["think"]) > 500 else row["think"]
            ledger.append(row)

    full_rows = [row for row in ledger if row["system_id"] == FULL_SYSTEM]
    clusters = Counter(row["reasoning_cluster"] for row in full_rows)
    target_counts = Counter(
        target for row in full_rows if row["predicted_route"] == "clarify" for target in row["clarification_targets"]
    )
    rule_counts = Counter(row["matched_rule_id"] or "none" for row in full_rows)
    examples = defaultdict(list)
    for row in sorted(full_rows, key=lambda item: item["record_id"]):
        bucket = examples[row["reasoning_cluster"]]
        if len(bucket) < 5:
            bucket.append(
                {
                    "record_id": row["record_id"],
                    "command": row["command"],
                    "gold_route": row["gold_route"],
                    "predicted_route": row["predicted_route"],
                    "clarification_question": row["clarification_question"],
                    "asked_slots_licensed_by_context": row["asked_slots_licensed_by_context"],
                    "think_excerpt": row["think_excerpt"],
                    "semantic_goal_correct": row["semantic_goal_correct"],
                    "goal_first_route": row["goal_first_route"],
                    "matched_rule_id": row["matched_rule_id"],
                }
            )

    gold_execute_clarify = [
        row for row in full_rows if row["gold_route"] == "execute" and row["predicted_route"] == "clarify"
    ]
    summary = {
        "claim_boundary": "reasoning extracted from frozen T39 raw_output; T39 not modified",
        "source_hashes": hashes,
        "n_full_manager": len(full_rows),
        "n_ledger_rows": len(ledger),
        "has_think_full": sum(row["has_think"] for row in full_rows),
        "think_closed_full": sum(row["think_closed"] for row in full_rows),
        "think_truncated_unclosed_full": sum(row["has_think"] and not row["think_closed"] for row in full_rows),
        "intent_summary_nonnull_full": sum(bool(row["intent_summary_frozen"]) for row in full_rows),
        "think_mentions_treat_as_request": sum(row["think_mentions_treat_as_request"] for row in full_rows),
        "think_reused_scene_facts": sum(bool(row["think_reused_scene_facts"]) for row in full_rows),
        "gold_execute_sent_to_clarify": len(gold_execute_clarify),
        "gold_execute_clarify_slots_licensed": sum(bool(row["asked_slots_licensed_by_context"]) for row in gold_execute_clarify),
        "gold_execute_clarify_knew_request_and_asked": sum(
            row["reasoning_cluster"] == "knew_it_was_a_request_but_asked_for_scene_slots" for row in gold_execute_clarify
        ),
        "goal_first_would_execute_those": sum(
            row.get("goal_first_route") == "execute" for row in gold_execute_clarify
        ),
        "reasoning_clusters_full_manager": dict(clusters),
        "clarify_target_counts_full": dict(target_counts.most_common(12)),
        "matched_rule_counts_full": dict(rule_counts.most_common()),
        "actionable_insights": [
            "Thinking already exists in frozen raw_output for every full-manager record; it was never lifted into a ledger.",
            "intent_summary is null on frozen T39, so the only native explanation of the run is the <think> block plus the clarification question.",
            "The dominant over-ask pattern is requesting destination/time/object slots that the scene or dialogue already licence.",
            "In many of those cases the model already says the nurse/housekeeper told it to treat the utterance as a request, then still asks.",
            "Goal-first routing would execute most of those gold-execute cases without a new model, because the model already described the job in <think>.",
        ],
        "examples_by_cluster": dict(examples),
    }
    slim_keys = [
        "record_id",
        "system_id",
        "command",
        "gold_route",
        "predicted_route",
        "gold_speech_act",
        "predicted_speech_act",
        "semantic_goal_correct",
        "speech_act_correct",
        "route_correct",
        "clarification_question",
        "clarification_targets",
        "asked_slots_licensed_by_context",
        "unresolved_slots",
        "capability_status",
        "risk_level",
        "matched_rule_id",
        "intent_summary_frozen",
        "goal_first_route",
        "think_mentions_treat_as_request",
        "think_reused_scene_facts",
        "has_think",
        "think_closed",
        "think_chars",
        "think",
        "think_excerpt",
        "reasoning_cluster",
        "scene_context",
        "dialogue_history",
    ]
    OUT_JSONL.write_text(
        "".join(json.dumps({key: row[key] for key in slim_keys}, ensure_ascii=False) + "\n" for row in ledger),
        encoding="utf-8",
    )
    OUT_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    printable = {k: summary[k] for k in summary if k != "examples_by_cluster"}
    print(json.dumps(printable, sort_keys=True))


if __name__ == "__main__":
    main()
