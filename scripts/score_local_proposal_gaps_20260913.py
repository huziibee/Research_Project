#!/usr/bin/env python3
"""Score proposal gaps that do not need a GPU.

Does not invent gold CPC or gold risk. Does not touch T39/T41.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD_INTENT = (
    ROOT
    / "pilot120_intent_evaluation_20260902"
    / "pilot120_intent_evaluation_20260902"
    / "data"
    / "intent_gold_references_120.jsonl"
)
GOLD_CORE = ROOT / "data" / "annotations" / "pilot_120_v1" / "pilot_120_final_gold.jsonl"
LANE = ROOT / "outputs" / "gfv2_local_lane_a_rows_20260912.jsonl"
V2_PRED = (
    ROOT
    / "outputs"
    / "cluster_pulls"
    / "r1_manager"
    / "predictions"
    / "goal_first_manager_v2.predictions.jsonl"
)
OUT = ROOT / "outputs" / "local_proposal_gaps_20260913.json"
SPEECH = (
    "directive_command",
    "indirect_request",
    "information_question",
    "permission_request",
    "prohibition",
    "conditional_directive",
    "multi_intent",
    "other_non_actionable",
)


def load_jsonl(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["record_id"]] = row
    return rows


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if (tp + fp) else None
    r = tp / (tp + fn) if (tp + fn) else None
    f = None
    if p is not None and r is not None and (p + r):
        f = 2 * p * r / (p + r)
    return {"precision": p, "recall": r, "f1": f, "tp": tp, "fp": fp, "fn": fn}


def main() -> None:
    intent = load_jsonl(GOLD_INTENT)
    core = load_jsonl(GOLD_CORE)
    lane = load_jsonl(LANE)
    pred = load_jsonl(V2_PRED)
    ids = sorted(core)
    assert len(ids) == 120

    gold_keys = Counter()
    for row in core.values():
        gold_keys.update(row.keys())

    exact = 0
    gold_counts = Counter()
    pred_counts = Counter()
    tp = Counter()
    for rid in ids:
        g = intent[rid].get("gold_speech_act") or ""
        p = lane[rid].get("speech_act") or ""
        gold_counts[g] += 1
        pred_counts[p] += 1
        if g == p:
            exact += 1
            tp[g] += 1
    per = {}
    f1s = []
    for lab in SPEECH:
        fn = gold_counts[lab] - tp[lab]
        fp = pred_counts[lab] - tp[lab]
        report = prf(tp[lab], fp, fn)
        report["gold_support"] = gold_counts[lab]
        per[lab] = report
        if gold_counts[lab] or pred_counts[lab]:
            if report["f1"] is not None:
                f1s.append(report["f1"])
    macro = sum(f1s) / len(f1s) if f1s else None

    filled = 0
    unknown = 0
    unassigned = 0
    slot_n = 0
    nonempty_frames = 0
    for rid in ids:
        cpc = ((pred[rid].get("parsed") or {}).get("analysis") or {}).get("cpc") or {}
        any_filled = False
        for slot in cpc.values():
            if not isinstance(slot, dict):
                continue
            slot_n += 1
            status = str(slot.get("status") or "")
            value = str(slot.get("value") or "")
            if status == "filled" and value and value != "unassigned":
                filled += 1
                any_filled = True
            if status == "unknown":
                unknown += 1
            if value == "unassigned":
                unassigned += 1
        if any_filled:
            nonempty_frames += 1

    payload = {
        "claim_boundary": (
            "Local read of existing files. Not a new GPU run. "
            "Pilot-120 gold has no CPC frames and no risk_level, so those "
            "proposal metrics cannot be scored even after a rerun."
        ),
        "gold_core_has_cpc": "cpc" in gold_keys or "gold_cpc" in gold_keys,
        "gold_core_has_risk_level": "risk_level" in gold_keys or "gold_risk_level" in gold_keys,
        "gold_core_field_names": sorted(gold_keys),
        "speech_act_new_goal_first": {
            "exact": exact,
            "n": 120,
            "exact_rate": exact / 120,
            "macro_f1_over_observed_labels": macro,
            "per_label": per,
            "source": "lane speech_act vs intent-gold gold_speech_act",
        },
        "cpc_emit_new_goal_first": {
            "rows_with_any_filled_slot": nonempty_frames,
            "filled_slots": filled,
            "unknown_slots": unknown,
            "unassigned_values": unassigned,
            "slot_observations": slot_n,
            "note": (
                "Frames exist as schema placeholders. Almost all values are "
                "unknown/unassigned. No gold CPC, so slot-binding F1 is blocked."
            ),
        },
        "risk_sensitive_decision_accuracy": {
            "status": "blocked_no_gold_risk",
            "reason": (
                "Evaluator definition is route-match on gold medium/high risk. "
                "pilot_120_final_gold.jsonl has no risk_level."
            ),
        },
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
