#!/usr/bin/env python3
"""Figures and closed-form tables for the live six systems, fixed order."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIGS = ROOT / "results" / "figures"
LANE = ROOT / "outputs" / "gfv2_local_lane_a_rows_20260912.jsonl"
GOLD = ROOT / "data" / "annotations" / "pilot_120_v1" / "pilot_120_final_gold.jsonl"
V2_EVAL = ROOT / "outputs" / "cluster_pulls" / "r1_manager" / "goal_first_manager_v2.eval.json"
V2_PRED = (
    ROOT / "outputs" / "cluster_pulls" / "r1_manager" / "predictions" / "goal_first_manager_v2.predictions.jsonl"
)
BA = ROOT / "outputs" / "base_vs_adapter_goal_trace_proxy_rows_20260911.jsonl"
OUT = ROOT / "outputs" / "live_six_closed_forms_20260913.json"
ROUTE_LABELS = ["execute", "clarify", "refuse"]

ORDER = [
    ("raw", "Raw Qwen"),
    ("ft", "Fine-tune"),
    ("gf", "New goal-first"),
    ("deg", "New degree"),
    ("timid", "New timid"),
    ("blind", "New context-blind"),
]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def canon(route: str | None) -> str:
    if route in {"face_preserving_rejection", "refuse"}:
        return "refuse"
    if route in {"silently_resolve", "execute"}:
        return "execute"
    if route == "clarify":
        return "clarify"
    return str(route or "")


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if (tp + fp) else None
    r = tp / (tp + fn) if (tp + fn) else None
    f = (2 * p * r / (p + r)) if p is not None and r is not None and (p + r) else None
    return {"precision": p, "recall": r, "f1": f, "tp": tp, "fp": fp, "fn": fn}


def style(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle=":", linewidth=0.6, alpha=0.7)
    ax.set_axisbelow(True)


def main() -> None:
    FIGS.mkdir(parents=True, exist_ok=True)
    lane = {row["record_id"]: row for row in load_jsonl(LANE)}
    gold = {row["record_id"]: row for row in load_jsonl(GOLD)}
    ba = {row["record_id"]: row for row in load_jsonl(BA)}
    ids = sorted(gold)
    v2_eval = json.loads(V2_EVAL.read_text(encoding="utf-8"))

    pred = {
        "raw": {rid: canon(ba[rid]["systems"]["direct_base_llm"]["predicted_route"]) for rid in ids},
        "ft": {rid: canon(ba[rid]["systems"]["t28_selected_adapter_llm"]["predicted_route"]) for rid in ids},
        "gf": {rid: canon(lane[rid]["goal_first"]) for rid in ids},
        "deg": {rid: canon(lane[rid]["degree"]) for rid in ids},
        "timid": {rid: canon(lane[rid]["rich"]) for rid in ids},
        "blind": {rid: canon(lane[rid]["blind"]) for rid in ids},
    }
    gold_route = {rid: canon(lane[rid]["gold_route"]) for rid in ids}

    ask = {}
    routing = {}
    refuse_when_gold_refuse = {}
    for key, _name in ORDER:
        tp = fp = fn = correct = 0
        gold_ref = pred_ref_on_gold_ref = 0
        for rid in ids:
            g, p = gold_route[rid], pred[key][rid]
            if p == g:
                correct += 1
            if g == "clarify" and p == "clarify":
                tp += 1
            if p == "clarify" and g != "clarify":
                fp += 1
            if g == "clarify" and p != "clarify":
                fn += 1
            if g == "refuse":
                gold_ref += 1
                if p == "refuse":
                    pred_ref_on_gold_ref += 1
        routing[key] = correct
        ask[key] = prf(tp, fp, fn)
        refuse_when_gold_refuse[key] = {"n": gold_ref, "refused": pred_ref_on_gold_ref}

    # Ambiguity over-predict: actual predicted bags, not reconstructed from F1
    gold_tags = Counter()
    for row in gold.values():
        gold_tags.update(row.get("ambiguity_types") or [])
    pred_tags = Counter()
    for row in load_jsonl(V2_PRED):
        pred_tags.update(row.get("ambiguity_types") or [])
    labels = sorted(set(gold_tags) | set(pred_tags), key=lambda k: gold_tags[k], reverse=True)

    unsafe_ids = [
        rid
        for rid, row in lane.items()
        if row.get("live_matched_rule") == "known_unsafe_or_prohibited"
        and not row.get("goal_first_correct")
        and rid in ids
    ]

    payload = {
        "system_order": [name for _, name in ORDER],
        "routing_correct_out_of_120": {name: routing[key] for key, name in ORDER},
        "clarification": {name: ask[key] for key, name in ORDER},
        "safe_rejection": {name: refuse_when_gold_refuse[key] for key, name in ORDER},
        "unsafe_rule_on_routing_wrong": sorted(unsafe_ids),
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    names = [name for _, name in ORDER]

    # Routing correctness, locked order
    fig, ax = plt.subplots(figsize=(14.5, 6.0))
    x = np.arange(len(names))
    vals = [routing[k] for k, _ in ORDER]
    colors = ["#1f4e79", "#1f4e79", "#2e7d32", "#2e7d32", "#2e7d32", "#2e7d32"]
    bars = ax.bar(x, vals, color=colors, width=0.62, edgecolor="white")
    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=11)
    ax.set_ylim(0, 128)
    ax.set_ylabel("Commands out of 120")
    ax.set_title(
        "Routing correctness: did we press gold’s button (do it / ask / refuse)?\n"
        "Same order as every table in this folder. This is not intent.",
        loc="left",
        fontsize=13,
    )
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 1.5, f"{val}/120", ha="center", fontsize=11)
    style(ax)
    fig.tight_layout()
    fig.savefig(FIGS / "routing-correct-wide.png", dpi=160, bbox_inches="tight")
    plt.close()

    # Routing confusion heatmaps
    fig, axes = plt.subplots(2, 3, figsize=(16.8, 10.4))
    for ax, (key, name) in zip(axes.ravel(), ORDER):
        mat = np.zeros((3, 3), dtype=int)
        idx = {lab: i for i, lab in enumerate(ROUTE_LABELS)}
        for rid in ids:
            g = gold_route[rid]
            p = pred[key][rid]
            if g in idx and p in idx:
                mat[idx[g], idx[p]] += 1
        im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=76)
        ax.set_xticks(range(3), ["Did it", "Asked", "Refused"], fontsize=8)
        ax.set_yticks(range(3), ["Gold did it", "Gold asked", "Gold refused"], fontsize=8)
        ax.set_title(name, fontsize=11)
        for i in range(3):
            for j in range(3):
                ax.text(j, i, str(mat[i, j]), ha="center", va="center", fontsize=11)
        ax.set_xlabel("What the system pressed")
    fig.suptitle(
        "Routing confusion (locked system order). Diagonal = routing correct. Off-diagonal = wrong button.",
        x=0.01,
        ha="left",
        fontsize=13,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(FIGS / "routing-confusion-heatmaps.png", dpi=160, bbox_inches="tight")
    plt.close()

    # Capability accuracy (degree/timid share goal-first analysis)
    fig, ax = plt.subplots(figsize=(14.5, 6.0))
    cap_names = ["Raw Qwen", "Fine-tune", "New goal-first\n(= degree = timid writing)", "New context-blind"]
    cap_vals = [0.667, 0.717, 0.425, 0.067]
    bars = ax.bar(np.arange(4), cap_vals, color=["#1f4e79", "#1f4e79", "#9e3a3a", "#9e3a3a"], width=0.55)
    ax.set_xticks(np.arange(4))
    ax.set_xticklabels(cap_names, fontsize=11)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Capability accuracy")
    ax.set_title(
        "Did the system’s capability bit match gold?\n"
        "New goal-first is worse than raw Qwen. That is why it refuses so much.",
        loc="left",
        fontsize=13,
    )
    for bar, val in zip(bars, cap_vals):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.02, f"{val:.3f}", ha="center", fontsize=11)
    style(ax)
    fig.tight_layout()
    fig.savefig(FIGS / "capability-accuracy-wide.png", dpi=160, bbox_inches="tight")
    plt.close()

    # 62 live rules
    fig, ax = plt.subplots(figsize=(13.2, 5.8))
    rule_names = [
        "Cannot do this\n(known_incapable)",
        "Ask by default\n(default_clarify)",
        "Unsafe / banned\n(known_unsafe…)",
        "Licensed do-it\n(context_licensed…)",
    ]
    rule_vals = [36, 13, 10, 3]
    bars = ax.bar(np.arange(4), rule_vals, color=["#9e3a3a", "#c47b17", "#7a2e2e", "#2e7d32"], width=0.55)
    ax.set_xticks(np.arange(4))
    ax.set_xticklabels(rule_names, fontsize=11)
    ax.set_ylabel("Rows inside the 62")
    ax.set_ylim(0, 42)
    ax.set_title(
        "Which live rule fired when writing was already right?\n"
        "36 wrong “cannot” bits, plus 10 unauthorized-as-unsafe refuses.",
        loc="left",
        fontsize=13,
    )
    for bar, val in zip(bars, rule_vals):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.6, str(val), ha="center", fontsize=12)
    style(ax)
    fig.tight_layout()
    fig.savefig(FIGS / "the-62-rules-wide.png", dpi=160, bbox_inches="tight")
    plt.close()

    # Clarification P vs R
    fig, ax = plt.subplots(figsize=(14.5, 6.2))
    x = np.arange(len(names))
    w = 0.36
    prec = [ask[k]["precision"] or 0 for k, _ in ORDER]
    rec = [ask[k]["recall"] or 0 for k, _ in ORDER]
    ax.bar(x - w / 2, prec, width=w, color="#1f4e79", label="Clarification precision")
    ax.bar(x + w / 2, rec, width=w, color="#c47b17", label="Clarification recall")
    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=11)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Score (0 to 1)")
    ax.set_title(
        "Did we press Ask when gold pressed Ask?\n"
        "Precision: of our asks, how many gold wanted. Recall: of gold asks, how many we asked.",
        loc="left",
        fontsize=13,
    )
    ax.legend(frameon=False)
    style(ax)
    fig.tight_layout()
    fig.savefig(FIGS / "clarification-pr-wide.png", dpi=160, bbox_inches="tight")
    plt.close()

    # Ambiguity gold vs predicted support (goal-first only)
    fig, ax = plt.subplots(figsize=(15.5, 7.2))
    pred_n = [pred_tags[lab] for lab in labels]
    gold_n = [gold_tags[lab] for lab in labels]
    y = np.arange(len(labels))
    ax.barh(y + 0.18, gold_n, height=0.36, color="#2e7d32", label="Gold count")
    ax.barh(y - 0.18, pred_n, height=0.36, color="#9e3a3a", label="New goal-first predicted count")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel("Rows out of 120 that carry this tag")
    ax.set_title(
        "Ambiguity tags: what gold used vs what new goal-first emitted\n"
        "action_order is the binge. Several gold-heavy names are almost never predicted.",
        loc="left",
        fontsize=13,
    )
    ax.legend(frameon=False)
    ax.invert_yaxis()
    style(ax)
    ax.grid(axis="x", linestyle=":", linewidth=0.6, alpha=0.7)
    fig.tight_layout()
    fig.savefig(FIGS / "ambiguity-overpredict-wide.png", dpi=160, bbox_inches="tight")
    plt.close()

    # Capability vs refuse on new goal-first
    cap_refuse = Counter()
    for rid in ids:
        gcap = gold[rid].get("capability_status")
        groute = gold_route[rid]
        proute = pred["gf"][rid]
        scap = lane[rid].get("capability_status")
        cap_refuse[(gcap, scap, groute, proute)] += 1
    # simpler stacked: gold capable rows, predicted route
    fig, ax = plt.subplots(figsize=(12.8, 6.0))
    cats = ["Gold capable\n(97 rows)", "Gold not capable\n(23 rows)"]
    execute = []
    askc = []
    refc = []
    for mask in (lambda c: c == "capable", lambda c: c != "capable"):
        e = a = r = 0
        for rid in ids:
            if not mask(gold[rid].get("capability_status")):
                continue
            p = pred["gf"][rid]
            if p == "execute":
                e += 1
            elif p == "clarify":
                a += 1
            else:
                r += 1
        execute.append(e)
        askc.append(a)
        refc.append(r)
    x = np.arange(2)
    ax.bar(x, execute, color="#2e7d32", label="Did it")
    ax.bar(x, askc, bottom=execute, color="#c47b17", label="Asked")
    ax.bar(x, refc, bottom=[a + b for a, b in zip(execute, askc)], color="#9e3a3a", label="Refused")
    ax.set_xticks(x)
    ax.set_xticklabels(cats, fontsize=12)
    ax.set_ylabel("Commands")
    ax.set_title(
        "New goal-first button vs gold capability\n"
        "Most refuses sit on gold-capable rows. That is the over-refuse, not a card that said no.",
        loc="left",
        fontsize=13,
    )
    ax.legend(frameon=False)
    style(ax)
    fig.tight_layout()
    fig.savefig(FIGS / "capability-vs-refuse-wide.png", dpi=160, bbox_inches="tight")
    plt.close()

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
