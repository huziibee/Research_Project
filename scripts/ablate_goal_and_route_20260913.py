"""Join goal-proxy and route correctness across base, adapter, and live v2.

Exploratory proxies only. Not official SGC. T39 leftover SGC is aggregate-only.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THRESH = "0.18"
V2_ROWS = ROOT / "outputs/gfv2_intent_summary_goal_trace_proxy_rows_20260912.jsonl"
BA_ROWS = ROOT / "outputs/base_vs_adapter_goal_trace_proxy_rows_20260911.jsonl"
LANE_ROWS = ROOT / "outputs/gfv2_local_lane_a_rows_20260912.jsonl"
OUT = ROOT / "outputs/goal_and_route_ablation_20260913.json"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def cell(goal: bool, route: bool) -> str:
    if goal and route:
        return "goal_right_route_right"
    if goal and not route:
        return "goal_right_route_wrong"
    if (not goal) and route:
        return "goal_wrong_route_right"
    return "goal_wrong_route_wrong"


def main() -> None:
    v2 = {row["record_id"]: row for row in load_jsonl(V2_ROWS)}
    ba = {row["record_id"]: row for row in load_jsonl(BA_ROWS)}
    lane = {row["record_id"]: row for row in load_jsonl(LANE_ROWS)}
    ids = sorted(set(v2) & set(ba) & set(lane))
    assert len(ids) == 120, len(ids)

    rows = []
    counts = {
        "v2": Counter(),
        "base": Counter(),
        "adapter": Counter(),
    }
    gold = Counter()
    v2_goal_right_base_route = Counter()
    v2_goal_right_adapter_route = Counter()
    v2_overask = []  # goal right, route wrong
    both_goal_v2_and_base = 0
    both_goal_v2_and_adapter = 0
    triple_goal = 0
    v2_goal_base_also_goal_and_route = 0
    v2_goal_adapter_also_goal_and_route = 0

    for rid in ids:
        vr = v2[rid]
        br = ba[rid]
        lr = lane[rid]
        gold_route = vr["gold_route"]
        gold[gold_route] += 1
        v2_goal = bool(vr["proxies"][THRESH]["proxy_correct"])
        v2_route = bool(vr["route_correct"])
        base = br["systems"]["direct_base_llm"]
        adp = br["systems"]["t28_selected_adapter_llm"]
        base_goal = bool(base["proxies"][THRESH]["proxy_correct"])
        base_route = bool(base["route_correct"])
        adp_goal = bool(adp["proxies"][THRESH]["proxy_correct"])
        adp_route = bool(adp["route_correct"])
        counts["v2"][cell(v2_goal, v2_route)] += 1
        counts["base"][cell(base_goal, base_route)] += 1
        counts["adapter"][cell(adp_goal, adp_route)] += 1
        if v2_goal and base_goal:
            both_goal_v2_and_base += 1
        if v2_goal and adp_goal:
            both_goal_v2_and_adapter += 1
        if v2_goal and base_goal and adp_goal:
            triple_goal += 1
        if v2_goal:
            v2_goal_right_base_route["correct" if base_route else "wrong"] += 1
            v2_goal_right_adapter_route["correct" if adp_route else "wrong"] += 1
            if base_goal and base_route:
                v2_goal_base_also_goal_and_route += 1
            if adp_goal and adp_route:
                v2_goal_adapter_also_goal_and_route += 1
        if v2_goal and not v2_route:
            v2_overask.append(
                {
                    "record_id": rid,
                    "gold_route": gold_route,
                    "v2_pred": vr["predicted_route"],
                    "base_pred": base["predicted_route"],
                    "base_route_correct": base_route,
                    "base_goal": base_goal,
                    "adapter_pred": adp["predicted_route"],
                    "adapter_route_correct": adp_route,
                    "adapter_goal": adp_goal,
                    "degree": lr["degree"],
                    "degree_correct": lr["degree_correct"],
                    "rich": lr["rich"],
                    "blind": lr["blind"],
                    "t39_full": lr["t39_full"],
                    "matched_rule": lr.get("live_matched_rule"),
                    "capability_status": lr.get("capability_status"),
                    "salvaged": vr.get("salvaged"),
                }
            )
        rows.append(
            {
                "record_id": rid,
                "gold_route": gold_route,
                "v2_goal": v2_goal,
                "v2_route": v2_route,
                "v2_pred": vr["predicted_route"],
                "base_goal": base_goal,
                "base_route": base_route,
                "base_pred": base["predicted_route"],
                "adapter_goal": adp_goal,
                "adapter_route": adp_route,
                "adapter_pred": adp["predicted_route"],
                "degree_correct": lr["degree_correct"],
                "rich_pred": lr["rich"],
                "blind_pred": lr["blind"],
                "t39_full": lr["t39_full"],
            }
        )

    overask_gold = Counter(r["gold_route"] for r in v2_overask)
    overask_v2_pred = Counter(r["v2_pred"] for r in v2_overask)
    overask_base_route_ok = sum(1 for r in v2_overask if r["base_route_correct"])
    overask_adapter_route_ok = sum(1 for r in v2_overask if r["adapter_route_correct"])
    overask_degree_ok = sum(1 for r in v2_overask if r["degree_correct"])
    overask_base_both = sum(1 for r in v2_overask if r["base_goal"] and r["base_route_correct"])
    overask_t39_clarify = sum(1 for r in v2_overask if r["t39_full"] == "clarify")

    dump = {
        "n": 120,
        "threshold": 0.18,
        "claim_boundary": (
            "Goal flags are exploratory lexical/polarity proxies, not official two-judge SGC. "
            "v2 proxy uses intent_summary; base/adapter use leftover think-trace text. "
            "Do not say v2 understands goals better than base because the artifacts differ."
        ),
        "two_by_two": counts,
        "headline": {
            "v2_goal": sum(counts["v2"][k] for k in ("goal_right_route_right", "goal_right_route_wrong")),
            "v2_route": sum(counts["v2"][k] for k in ("goal_right_route_right", "goal_wrong_route_right")),
            "base_goal": sum(counts["base"][k] for k in ("goal_right_route_right", "goal_right_route_wrong")),
            "base_route": sum(counts["base"][k] for k in ("goal_right_route_right", "goal_wrong_route_right")),
            "adapter_goal": sum(counts["adapter"][k] for k in ("goal_right_route_right", "goal_right_route_wrong")),
            "adapter_route": sum(counts["adapter"][k] for k in ("goal_right_route_right", "goal_wrong_route_right")),
        },
        "overlap_when_v2_goal_right": {
            "n": sum(counts["v2"][k] for k in ("goal_right_route_right", "goal_right_route_wrong")),
            "also_base_goal": both_goal_v2_and_base,
            "also_adapter_goal": both_goal_v2_and_adapter,
            "also_both_base_and_adapter_goal": triple_goal,
            "base_route_correct": dict(v2_goal_right_base_route),
            "adapter_route_correct": dict(v2_goal_right_adapter_route),
            "base_goal_and_route_both": v2_goal_base_also_goal_and_route,
            "adapter_goal_and_route_both": v2_goal_adapter_also_goal_and_route,
        },
        "overask_v2_goal_right_route_wrong": {
            "n": len(v2_overask),
            "gold": dict(overask_gold),
            "v2_predicted": dict(overask_v2_pred),
            "base_got_the_route": overask_base_route_ok,
            "adapter_got_the_route": overask_adapter_route_ok,
            "degree_got_the_route": overask_degree_ok,
            "base_goal_and_route_both": overask_base_both,
            "t39_full_said_clarify": overask_t39_clarify,
            "ids": [r["record_id"] for r in v2_overask],
        },
        "t39_leftover_sgc_aggregate_only": {
            "full_manager_sgc": 113,
            "full_manager_route": 33,
            "full_manager_sgc_right_route_wrong": 83,
            "context_blind_sgc": 95,
            "context_blind_route": 23,
            "note": "Official leftover think-trace SGC. T39 never filled intent_summary. Not joined per-id in this dump.",
        },
        "what_we_ran": {
            "pilot120_full_context": [
                "T39 direct base (route 88)",
                "T39 unofficial adapter (route 87)",
                "T39 full manager (route 33, leftover SGC 113)",
                "T39 degree (route 51, leftover SGC 113)",
                "v2 goal-first (route 54, intent_summary proxy 112)",
                "v2 degree (route 59, same analyses as goal-first)",
                "v2 rich-conservative (route 26, same analyses)",
            ],
            "pilot120_context_blind": [
                "T39 context-blind manager (route 23 = always-clarify band, leftover SGC 95)",
                "v2 context-blind (route 21 = always-refuse band; same prompt, no scene/dialogue/capability card)",
            ],
            "not_this_join": "Natives VAGUE/AmbiK/Indirect/CLARA are different labels. Do not pool.",
        },
    }
    OUT.write_text(json.dumps(dump, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "two_by_two": {k: dict(v) for k, v in counts.items()}, "overask_n": len(v2_overask)}, indent=2))


if __name__ == "__main__":
    main()
