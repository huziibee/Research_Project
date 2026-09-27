#!/usr/bin/env python3
"""Post-freeze T39 semantic-intent reporting omitted by the supplied package.

This program requires already frozen final judgments.  It never writes them and
does not alter the sealed map, T39, or T41.  Layer allocation uses only T41's
frozen per-record CPC-exact evidence.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

SYSTEMS = (("degree_based_router", "FULL_CONTEXT_SHARED"), ("full_type_risk_aware_manager", "FULL_CONTEXT_SHARED"), ("context_blind_manager", "CONTEXT_BLIND"))
FIELDS = ("primary_goal_match", "required_action_set_match", "polarity_match", "explicit_enough", "no_incompatible_goal")


def jsonl(path: str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def wilson(k: int, n: int) -> list[float] | None:
    if not n:
        return None
    z = 1.959963984540054
    p = k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / den
    return [max(0, center - half), min(1, center + half)]


def rate(rows: list[dict], field: str) -> dict:
    n = len(rows)
    k = sum(bool(row[field]) for row in rows)
    return {"n": n, "correct": k, "rate": k / n if n else None, "wilson95": wilson(k, n)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judgments", required=True)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--intent-gold", required=True)
    parser.add_argument("--core-gold", required=True)
    parser.add_argument("--review-root", required=True)
    parser.add_argument("--t41-score-root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--route-error-ledger", required=True)
    parser.add_argument("--sgc-route-wrong-ledger", required=True)
    args = parser.parse_args()

    judgments = {row["evaluation_id"]: row for row in jsonl(args.judgments)}
    mapping = {row["evaluation_id"]: row for row in jsonl(args.mapping)}
    if set(judgments) != set(mapping):
        raise SystemExit("judgment_mapping_id_mismatch")
    intent_gold = {row["record_id"]: row for row in jsonl(args.intent_gold)}
    core_gold = {row["record_id"]: row for row in jsonl(args.core_gold)}
    review = Path(args.review_root) / "cluster_outputs" / "R1" / "manager" / "predictions"
    t41_root = Path(args.t41_score_root)
    t41: dict[str, dict[str, dict]] = {}
    for system, _ in SYSTEMS:
        with (t41_root / f"{system}_complete_row_scores.csv").open(encoding="utf-8", newline="") as handle:
            t41[system] = {row["record_id"]: row for row in csv.DictReader(handle)}

    semantic = {(mapping[eid]["record_id"], mapping[eid]["analysis_condition"]): judgment for eid, judgment in judgments.items()}
    all_rows: list[dict] = []
    for system, condition in SYSTEMS:
        predictions = {row["record_id"]: row for row in jsonl(str(review / f"{system}.predictions.jsonl"))}
        for record_id, gold in intent_gold.items():
            decision = semantic[(record_id, condition)]
            prediction = predictions[record_id]
            sgc = all(bool(decision[field]) for field in FIELDS)
            speech_ok = prediction["parsed"]["analysis"]["speech_act"] == gold["gold_speech_act"]
            route_ok = prediction["terminal_strategy"] == core_gold[record_id]["terminal_strategy"]
            cpc_exact = t41[system][record_id]["cpc_exact"].strip().lower() == "true"
            layer = None
            if not route_ok:
                if not sgc:
                    layer = "Layer_1_semantic_goal_wrong"
                elif not speech_ok:
                    layer = "Layer_2_semantic_goal_correct_speech_act_wrong"
                elif not cpc_exact:
                    layer = "Layer_3_goal_and_speech_act_correct_CPC_or_resolution_wrong"
                else:
                    layer = "Layer_4_interpretation_sufficient_router_or_policy_wrong"
            all_rows.append({
                "record_id": record_id, "system_id": system, "analysis_condition": condition,
                "gold_speech_act": gold["gold_speech_act"],
                "predicted_speech_act": prediction["parsed"]["analysis"]["speech_act"],
                "speech_act_correct": speech_ok, "semantic_goal_correct": sgc,
                "full_intent_correct": bool(sgc and speech_ok), "cpc_exact_frozen_t41": cpc_exact,
                "route_correct": route_ok, "gold_terminal_strategy": core_gold[record_id]["terminal_strategy"],
                "terminal_strategy": prediction["terminal_strategy"], "root_failure_layer": layer,
                "semantic_component_score": sum(bool(decision[field]) for field in FIELDS) / len(FIELDS),
            })
    route_errors = [row for row in all_rows if not row["route_correct"]]
    sgc_route_wrong = [row for row in route_errors if row["semantic_goal_correct"]]
    for target, rows in ((Path(args.route_error_ledger), route_errors), (Path(args.sgc_route_wrong_ledger), sgc_route_wrong)):
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(all_rows[0]))
            writer.writeheader(); writer.writerows(rows)
    report: dict[str, object] = {"claim_boundary": "observable_semantic_goal_trace_correctness; completed prediction-blind model-judged addendum, not official correctness absent governance approval", "systems": {}}
    systems: dict[str, object] = {}
    for system, _ in SYSTEMS:
        rows = [row for row in all_rows if row["system_id"] == system]
        indirect = [row for row in rows if row["gold_speech_act"] == "indirect_request"]
        per_intent_class = {}
        for label in sorted({row["gold_speech_act"] for row in rows}):
            slice_rows = [row for row in rows if row["gold_speech_act"] == label]
            per_intent_class[label] = {
                "sgc": rate(slice_rows, "semantic_goal_correct"),
                "saa": rate(slice_rows, "speech_act_correct"),
                "fic": rate(slice_rows, "full_intent_correct"),
                "route_correct_given_sgc": rate([row for row in slice_rows if row["semantic_goal_correct"]], "route_correct"),
            }
        wrong = [row for row in rows if not row["route_correct"]]
        goal_right = [row for row in rows if row["semantic_goal_correct"]]
        matrix = Counter((row["semantic_goal_correct"], row["route_correct"]) for row in rows)
        systems[system] = {
            "sgc": rate(rows, "semantic_goal_correct"), "saa": rate(rows, "speech_act_correct"), "fic": rate(rows, "full_intent_correct"),
            "mean_component_score_diagnostic_only": sum(row["semantic_component_score"] for row in rows) / len(rows),
            "per_intent_class": per_intent_class,
            "indirect_request": {"sgc": rate(indirect, "semantic_goal_correct"), "saa": rate(indirect, "speech_act_correct"), "fic": rate(indirect, "full_intent_correct"), "route_correct_given_sgc": rate([row for row in indirect if row["semantic_goal_correct"]], "route_correct")},
            "intent_x_route": {
                "sgc_correct_route_correct": matrix[(True, True)], "sgc_correct_route_wrong": matrix[(True, False)],
                "sgc_wrong_route_correct": matrix[(False, True)], "sgc_wrong_route_wrong": matrix[(False, False)],
                "P_sgc_correct_given_route_wrong": sum(row["semantic_goal_correct"] for row in wrong) / len(wrong) if wrong else None,
                "P_route_wrong_given_sgc_correct": sum(not row["route_correct"] for row in goal_right) / len(goal_right) if goal_right else None,
            },
            "root_failure_layers_for_route_errors": dict(Counter(row["root_failure_layer"] for row in rows if row["root_failure_layer"])),
        }
    report["systems"] = systems
    report["record_counts"] = {"all_system_rows": len(all_rows), "route_error_rows": len(route_errors), "sgc_correct_route_wrong_rows": len(sgc_route_wrong)}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
