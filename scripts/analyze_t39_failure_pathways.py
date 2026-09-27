#!/usr/bin/env python3
"""Analyze frozen T39 observable-intent/route pathways without altering evidence."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        result = list(csv.DictReader(handle))
    for row in result:
        for field in ("speech_act_correct", "semantic_goal_correct", "full_intent_correct", "route_correct"):
            row[field] = row[field] == "True"
    return result


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def wilson(k: int, n: int, z: float = 1.959963984540054) -> list[float] | None:
    if not n:
        return None
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / den
    return [max(0.0, centre - half), min(1.0, centre + half)]


def proportion(k: int, n: int) -> dict:
    return {"correct": k, "n": n, "rate": k / n if n else None, "wilson95": wilson(k, n)}


def mcnemar(left: list[bool], right: list[bool]) -> dict:
    b = sum(a and not c for a, c in zip(left, right))
    c = sum(not a and c for a, c in zip(left, right))
    n = b + c
    p = 1.0 if not n else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / (2 ** n))
    return {"left_only_correct": b, "right_only_correct": c, "discordant": n, "exact_two_sided_p": p}


def association(rows: list[dict]) -> dict:
    # a=both correct, b=goal only, c=route only, d=neither.
    a = sum(x["semantic_goal_correct"] and x["route_correct"] for x in rows)
    b = sum(x["semantic_goal_correct"] and not x["route_correct"] for x in rows)
    c = sum(not x["semantic_goal_correct"] and x["route_correct"] for x in rows)
    d = sum(not x["semantic_goal_correct"] and not x["route_correct"] for x in rows)
    denominator = math.sqrt((a + b) * (c + d) * (a + c) * (b + d))
    phi = (a * d - b * c) / denominator if denominator else None
    odds_ratio_haldane = ((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5))
    return {
        "sgc_correct_route_correct": a, "sgc_correct_route_wrong": b,
        "sgc_wrong_route_correct": c, "sgc_wrong_route_wrong": d,
        "phi_sgc_route": phi,
        "odds_ratio_haldane_anscombe": odds_ratio_haldane,
        "p_route_correct_given_sgc_correct": a / (a + b) if a + b else None,
        "p_route_correct_given_sgc_wrong": c / (c + d) if c + d else None,
    }


def system_summary(rows: list[dict], gold: dict[str, dict]) -> dict:
    n = len(rows)
    states = Counter((x["semantic_goal_correct"], x["speech_act_correct"], x["route_correct"]) for x in rows)
    by_count: dict[str, dict] = {}
    for count in sorted({len(gold[x["record_id"]]["ambiguity_types"]) for x in rows}):
        subset = [x for x in rows if len(gold[x["record_id"]]["ambiguity_types"]) == count]
        by_count[str(count)] = {
            "n": len(subset),
            "sgc": proportion(sum(x["semantic_goal_correct"] for x in subset), len(subset)),
            "saa": proportion(sum(x["speech_act_correct"] for x in subset), len(subset)),
            "fic": proportion(sum(x["full_intent_correct"] for x in subset), len(subset)),
            "route": proportion(sum(x["route_correct"] for x in subset), len(subset)),
        }
    by_type: dict[str, dict] = {}
    all_types = sorted({t for x in rows for t in gold[x["record_id"]]["ambiguity_types"]})
    for ambiguity_type in all_types:
        subset = [x for x in rows if ambiguity_type in gold[x["record_id"]]["ambiguity_types"]]
        by_type[ambiguity_type] = {
            "n": len(subset),
            "sgc_rate": sum(x["semantic_goal_correct"] for x in subset) / len(subset),
            "route_rate": sum(x["route_correct"] for x in subset) / len(subset),
            "sgc_correct_route_wrong": sum(x["semantic_goal_correct"] and not x["route_correct"] for x in subset),
        }
    by_terminal: dict[str, dict] = {}
    for strategy in sorted({x["gold_terminal_strategy"] for x in rows}):
        subset = [x for x in rows if x["gold_terminal_strategy"] == strategy]
        by_terminal[strategy] = {
            "n": len(subset),
            "sgc": proportion(sum(x["semantic_goal_correct"] for x in subset), len(subset)),
            "route": proportion(sum(x["route_correct"] for x in subset), len(subset)),
            "fic": proportion(sum(x["full_intent_correct"] for x in subset), len(subset)),
        }
    return {
        "n": n,
        "pathway_state_counts": {f"SGC={sgc}|SAA={saa}|ROUTE={route}": count for (sgc, saa, route), count in sorted(states.items())},
        "sgc_route_association": association(rows),
        "correct_route_despite_wrong_sgc": proportion(sum(x["route_correct"] and not x["semantic_goal_correct"] for x in rows), n),
        "correct_route_despite_incomplete_full_intent": proportion(sum(x["route_correct"] and not x["full_intent_correct"] for x in rows), n),
        "wrong_route_despite_full_intent_correct": proportion(sum(not x["route_correct"] and x["full_intent_correct"] for x in rows), n),
        "by_ambiguity_count": by_count,
        "by_ambiguity_type_overlapping": by_type,
        "by_gold_terminal_strategy": by_terminal,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError(f"output_exists:{args.out}")
    data = read_csv(args.rows)
    gold = {row["record_id"]: row for row in read_jsonl(args.gold)}
    if len(data) != 360 or len(gold) != 120 or {x["record_id"] for x in data} != set(gold):
        raise ValueError("frozen_coverage_mismatch")
    systems = {name: sorted([x for x in data if x["system_id"] == name], key=lambda x: x["record_id"]) for name in sorted({x["system_id"] for x in data})}
    comparisons = {}
    for left, right in (("full_manager", "context_blind_manager"), ("degree_based_router", "full_manager"), ("degree_based_router", "context_blind_manager")):
        if left not in systems or right not in systems:
            continue
        if [x["record_id"] for x in systems[left]] != [x["record_id"] for x in systems[right]]:
            raise ValueError("paired_record_order_mismatch")
        comparisons[f"{left}_vs_{right}"] = {
            "sgc": mcnemar([x["semantic_goal_correct"] for x in systems[left]], [x["semantic_goal_correct"] for x in systems[right]]),
            "saa": mcnemar([x["speech_act_correct"] for x in systems[left]], [x["speech_act_correct"] for x in systems[right]]),
            "fic": mcnemar([x["full_intent_correct"] for x in systems[left]], [x["full_intent_correct"] for x in systems[right]]),
            "route": mcnemar([x["route_correct"] for x in systems[left]], [x["route_correct"] for x in systems[right]]),
        }
    result = {
        "analysis_id": "t39_frozen_failure_pathways_v1",
        "claim_boundary": "observable semantic goal trace and terminal route only; task execution success NOT_COMPUTED; overlapping ambiguity-type slices are descriptive",
        "source_hashes": {"final_intent_rows_csv": hashlib.sha256(args.rows.read_bytes()).hexdigest(), "pilot120_gold_jsonl": hashlib.sha256(args.gold.read_bytes()).hexdigest()},
        "systems": {name: system_summary(rows, gold) for name, rows in systems.items()},
        "paired_system_comparisons": comparisons,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": "PASS", "systems": list(systems), "sha256": hashlib.sha256(args.out.read_bytes()).hexdigest()}, sort_keys=True))


if __name__ == "__main__":
    main()
