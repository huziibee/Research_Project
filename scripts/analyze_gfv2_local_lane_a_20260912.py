#!/usr/bin/env python3
"""Local Lane A gaps for goal-first v2: licensed reroute, autopsy, intent proxy.

CPU only. Does not submit GPU jobs. Does not overwrite follow-on native predictions.
Salvage is post-rebuild. Natives are not pooled with Pilot-120. T39/T41 frozen.
Adapter unofficial. Goal-trace proxy is exploratory, not official two-judge SGC.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(
    0,
    str(ROOT / "pilot120_intent_evaluation_20260902" / "pilot120_intent_evaluation_20260902" / "scripts"),
)

from ambiguity_manager.systems.contracts import StructuredAnalysis  # noqa: E402
from ambiguity_manager.systems.routing import (  # noqa: E402
    DeterministicRouter,
    POLICY_GOAL_FIRST_V2,
    POLICY_GOAL_FIRST_V2_GOAL_LICENSED,
)
from intent_eval_common import wilson_interval  # noqa: E402
from score_base_vs_adapter_goal_trace_proxy_20260911 import (  # noqa: E402
    content_tokens,
    jaccard,
    polarity_conflict,
)

GOLD = ROOT / "data" / "annotations" / "pilot_120_v1" / "pilot_120_final_gold.jsonl"
INTENT_GOLD = (
    ROOT
    / "pilot120_intent_evaluation_20260902"
    / "pilot120_intent_evaluation_20260902"
    / "data"
    / "intent_gold_references_120.jsonl"
)
PULLS = ROOT / "outputs" / "cluster_pulls"
BASE_PROXY = ROOT / "outputs" / "base_vs_adapter_goal_trace_proxy_20260911.json"
T39_FULL = (
    ROOT
    / "review_bundles"
    / "pilot120_t39_20260902"
    / "cluster_outputs"
    / "R1"
    / "manager"
    / "predictions"
    / "full_type_risk_aware_manager.predictions.jsonl"
)
T39_DEGREE = (
    ROOT
    / "review_bundles"
    / "pilot120_t39_20260902"
    / "cluster_outputs"
    / "R1"
    / "manager"
    / "predictions"
    / "degree_based_router.predictions.jsonl"
)
T39_BLIND = (
    ROOT
    / "review_bundles"
    / "pilot120_t39_20260902"
    / "cluster_outputs"
    / "R1"
    / "manager"
    / "predictions"
    / "context_blind_manager.predictions.jsonl"
)

LIVE_SYSTEMS = (
    "goal_first_manager_v2",
    "degree_based_router_v2",
    "rich_conservative_manager_v2",
    "goal_first_context_blind_v2",
)
QUESTION_SHAPED = frozenset({"information_question", "other_non_actionable"})
THRESHOLDS = (0.12, 0.18, 0.25)
PRIMARY_THRESHOLD = 0.18
OUT_SUMMARY = ROOT / "outputs" / "gfv2_local_lane_a_20260912.json"
OUT_ROWS = ROOT / "outputs" / "gfv2_local_lane_a_rows_20260912.jsonl"
OUT_PROXY = ROOT / "outputs" / "gfv2_intent_summary_goal_trace_proxy_20260912.json"
OUT_PROXY_ROWS = ROOT / "outputs" / "gfv2_intent_summary_goal_trace_proxy_rows_20260912.jsonl"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rid = row["record_id"]
        if rid in rows:
            raise SystemExit(f"duplicate:{path}:{rid}")
        rows[rid] = row
    return rows


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


def analysis_from_pred(pred: dict) -> StructuredAnalysis:
    raw = (pred.get("parsed") or {}).get("analysis") or {}
    return StructuredAnalysis.from_dict(raw)


def confusion_counts(pairs: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    table: dict[str, dict[str, int]] = {}
    for gold, pred in pairs:
        table.setdefault(gold, {})
        table[gold][pred] = table[gold].get(pred, 0) + 1
    return table


def slice_stats(rows: list[dict], pred_key: str) -> dict:
    gold_exec = [r for r in rows if r["gold_route"] == "execute"]
    gold_ref = [r for r in rows if r["gold_route"] == "refuse"]
    gold_cla = [r for r in rows if r["gold_route"] == "clarify"]
    preds = [r[pred_key] for r in rows]
    return {
        "n": len(rows),
        "n_correct": sum(r[pred_key] == r["gold_route"] for r in rows),
        "accuracy": sum(r[pred_key] == r["gold_route"] for r in rows) / len(rows),
        "pred_counts": dict(Counter(preds)),
        "confusion_gold_to_pred": confusion_counts([(r["gold_route"], r[pred_key]) for r in rows]),
        "execute_recall_gold76": {
            "correct": sum(r[pred_key] == "execute" for r in gold_exec),
            "n": len(gold_exec),
        },
        "false_execute_on_gold_refuse": sum(r[pred_key] == "execute" for r in gold_ref),
        "false_execute_on_gold_clarify": sum(r[pred_key] == "execute" for r in gold_cla),
        "pred_execute": sum(p == "execute" for p in preds),
        "pred_clarify": sum(p == "clarify" for p in preds),
        "pred_refuse": sum(p == "refuse" for p in preds),
        "gold_execute_to": dict(Counter(r[pred_key] for r in gold_exec)),
        "gold_refuse_to": dict(Counter(r[pred_key] for r in gold_ref)),
        "gold_clarify_to": dict(Counter(r[pred_key] for r in gold_cla)),
        "execute_precision": (
            sum(r[pred_key] == "execute" and r["gold_route"] == "execute" for r in rows)
            / max(1, sum(p == "execute" for p in preds))
        ),
    }


def pairwise(rows: list[dict], left: str, right: str) -> dict:
    return {
        "route_agree": sum(r[left] == r[right] for r in rows),
        "both_correct": sum(r[left] == r["gold_route"] and r[right] == r["gold_route"] for r in rows),
        "left_only_correct": sum(
            r[left] == r["gold_route"] and r[right] != r["gold_route"] for r in rows
        ),
        "right_only_correct": sum(
            r[right] == r["gold_route"] and r[left] != r["gold_route"] for r in rows
        ),
    }


def replica_dirs() -> dict[str, Path]:
    found = {}
    for name, path in (
        ("R1", PULLS / "r1_manager"),
        ("R2", PULLS / "r2_manager"),
        ("R3", PULLS / "r3_manager"),
    ):
        pred_dir = path / "predictions"
        gf = pred_dir / "goal_first_manager_v2.predictions.jsonl"
        if gf.exists():
            found[name] = path
    return found


def load_replica(manager_dir: Path) -> dict[str, dict[str, dict]]:
    pred_dir = manager_dir / "predictions"
    out = {}
    for system in LIVE_SYSTEMS:
        path = pred_dir / f"{system}.predictions.jsonl"
        if not path.exists():
            raise SystemExit(f"missing_predictions:{path}")
        rows = load_jsonl(path)
        if len(rows) != 120:
            raise SystemExit(f"unexpected_n:{path}:{len(rows)}")
        out[system] = rows
    return out


def repaired_ids(manager_dir: Path, system: str) -> list[str]:
    manifest = json.loads((manager_dir / "run_manifest.json").read_text(encoding="utf-8"))
    return list((manifest.get("repaired") or {}).get(system) or [])


def proxy_pass(excerpt: str, gold_a: str, gold_b: str, threshold: float) -> dict:
    ta = content_tokens(excerpt)
    ga = content_tokens(gold_a)
    gb = content_tokens(gold_b)
    ja = jaccard(ta, ga)
    jb = jaccard(ta, gb)
    best = max(ja, jb)
    gold_best = gold_a if ja >= jb else gold_b
    empty = not excerpt.strip()
    conflict = (not empty) and polarity_conflict(excerpt, gold_best)
    ok = (not empty) and (not conflict) and best >= threshold
    return {
        "proxy_correct": ok,
        "overlap_best": best,
        "overlap_a": ja,
        "overlap_b": jb,
        "excerpt_empty": empty,
        "polarity_conflict": conflict,
        "excerpt_chars": len(excerpt or ""),
    }


def summarize_proxy(flags: list[bool], overlaps: list[float], empties: list[bool], conflicts: list[bool]) -> dict:
    n = len(flags)
    correct = sum(flags)
    return {
        "n": n,
        "proxy_correct": correct,
        "proxy_rate": correct / n,
        "wilson95": wilson_interval(correct, n),
        "mean_overlap": sum(overlaps) / n,
        "empty_excerpts": sum(empties),
        "polarity_conflicts": sum(conflicts),
    }


def main() -> None:
    gold = load_jsonl(GOLD)
    intent = load_jsonl(INTENT_GOLD)
    gold_routes = {rid: norm_route(row["terminal_strategy"]) for rid, row in gold.items()}
    if set(gold_routes) != set(intent) or len(gold_routes) != 120:
        raise SystemExit("gold_id_binding_failed")
    gold_hash = sha256_file(GOLD)
    if not gold_hash.startswith("5e23ad1a"):
        raise SystemExit(f"unexpected_gold_hash:{gold_hash}")

    replicas = replica_dirs()
    if "R1" not in replicas:
        raise SystemExit("r1_predictions_missing")

    t39 = {}
    for label, path in (
        ("t39_full_manager", T39_FULL),
        ("t39_degree", T39_DEGREE),
        ("t39_blind", T39_BLIND),
    ):
        if path.exists():
            t39[label] = {
                rid: norm_route(row.get("terminal_strategy"))
                for rid, row in load_jsonl(path).items()
            }

    frozen_base_proxy = None
    if BASE_PROXY.exists():
        frozen_base_proxy = json.loads(BASE_PROXY.read_text(encoding="utf-8"))

    replica_payload = {}
    primary_rows: list[dict] = []
    licensed_by_replica = {}

    for replica, manager_dir in replicas.items():
        preds = load_replica(manager_dir)
        gf = preds["goal_first_manager_v2"]
        salvaged = set(repaired_ids(manager_dir, "goal_first_manager_v2"))
        router_v2 = DeterministicRouter(policy=POLICY_GOAL_FIRST_V2)
        router_lic = DeterministicRouter(policy=POLICY_GOAL_FIRST_V2_GOAL_LICENSED)
        rows = []
        sanity_mismatch = []
        licensed_flips = []
        for rid in sorted(gold_routes):
            analysis = analysis_from_pred(gf[rid])
            live = norm_route(gf[rid].get("terminal_strategy"))
            rebuilt = norm_route(router_v2.route(analysis).recommended_strategy.value)
            licensed_decision = router_lic.route(analysis)
            licensed = norm_route(licensed_decision.recommended_strategy.value)
            if rebuilt != live:
                sanity_mismatch.append(rid)
            note_licensed = "goal_licensed_despite_question_shaped_speech_act" in (
                licensed_decision.notes or []
            )
            if licensed != live:
                licensed_flips.append(
                    {
                        "record_id": rid,
                        "gold_route": gold_routes[rid],
                        "live_goal_first": live,
                        "goal_licensed": licensed,
                        "speech_act": analysis.speech_act,
                        "intent_summary": (analysis.intent_summary or "")[:240],
                        "matched_rule_id": licensed_decision.matched_rule_id,
                        "notes": list(licensed_decision.notes or []),
                    }
                )
            live_correct = live == gold_routes[rid]
            rows.append(
                {
                    "record_id": rid,
                    "replica": replica,
                    "gold_route": gold_routes[rid],
                    "goal_first": live,
                    "goal_licensed": licensed,
                    "degree": norm_route(preds["degree_based_router_v2"][rid].get("terminal_strategy")),
                    "rich": norm_route(
                        preds["rich_conservative_manager_v2"][rid].get("terminal_strategy")
                    ),
                    "blind": norm_route(
                        preds["goal_first_context_blind_v2"][rid].get("terminal_strategy")
                    ),
                    "t39_full": (t39.get("t39_full_manager") or {}).get(rid),
                    "t39_degree": (t39.get("t39_degree") or {}).get(rid),
                    "t39_blind": (t39.get("t39_blind") or {}).get(rid),
                    "speech_act": analysis.speech_act,
                    "question_shaped_speech_act": (analysis.speech_act or "") in QUESTION_SHAPED,
                    "intent_summary": analysis.intent_summary,
                    "capability_status": (
                        analysis.capability_status.value if analysis.capability_status else None
                    ),
                    "risk_level": analysis.risk_level.value if analysis.risk_level else None,
                    "pilot_capability": next(
                        (
                            str(f).split(":", 1)[1]
                            for f in analysis.findings
                            if str(f).startswith("pilot_capability_status:")
                        ),
                        None,
                    ),
                    "live_matched_rule": (
                        ((gf[rid].get("parsed") or {}).get("runtime_metadata") or {})
                        .get("router_trace")
                        or {}
                    ).get("matched_rule_id"),
                    "licensed_matched_rule": licensed_decision.matched_rule_id,
                    "licensed_notes": list(licensed_decision.notes or []),
                    "licensed_flip": licensed != live,
                    "goal_licensed_note": note_licensed,
                    "salvaged": rid in salvaged,
                    "goal_first_correct": live_correct,
                    "goal_licensed_correct": licensed == gold_routes[rid],
                    "degree_correct": norm_route(
                        preds["degree_based_router_v2"][rid].get("terminal_strategy")
                    )
                    == gold_routes[rid],
                }
            )
        if replica == "R1":
            primary_rows = rows
        licensed_by_replica[replica] = {
            "n_predictions": 120,
            "rebuilt_v2_matches_live": 120 - len(sanity_mismatch),
            "rebuilt_v2_mismatches": sanity_mismatch,
            "goal_first": slice_stats(rows, "goal_first"),
            "goal_licensed": slice_stats(rows, "goal_licensed"),
            "degree": slice_stats(rows, "degree"),
            "rich": slice_stats(rows, "rich"),
            "blind": slice_stats(rows, "blind"),
            "licensed_minus_live": {
                "n_route_flips": len(licensed_flips),
                "flip_ids": [x["record_id"] for x in licensed_flips],
                "flips": licensed_flips,
                "n_goal_licensed_note": sum(r["goal_licensed_note"] for r in rows),
            },
            "pairwise": {
                "goal_licensed_vs_goal_first": pairwise(rows, "goal_licensed", "goal_first"),
                "goal_licensed_vs_degree": pairwise(rows, "goal_licensed", "degree"),
                "goal_licensed_vs_rich": pairwise(rows, "goal_licensed", "rich"),
                "goal_licensed_vs_blind": pairwise(rows, "goal_licensed", "blind"),
                "goal_first_vs_degree": pairwise(rows, "goal_first", "degree"),
                "goal_first_vs_rich": pairwise(rows, "goal_first", "rich"),
                "goal_first_vs_t39_full": pairwise(rows, "goal_first", "t39_full")
                if all(r.get("t39_full") for r in rows)
                else None,
            },
            "salvaged_ids": sorted(salvaged),
            "question_shaped_n": sum(r["question_shaped_speech_act"] for r in rows),
        }
        replica_payload[replica] = {
            "manager_dir": str(manager_dir.relative_to(ROOT)).replace("\\", "/"),
            "prediction_sha256": {
                system: sha256_file(manager_dir / "predictions" / f"{system}.predictions.jsonl")
                for system in LIVE_SYSTEMS
            },
            **licensed_by_replica[replica],
        }

    # Compact error autopsy on R1 (routes already R1=R2=R3 120/120).
    degree_only = [
        r
        for r in primary_rows
        if r["degree_correct"] and not r["goal_first_correct"]
    ]
    gf_only = [
        r
        for r in primary_rows
        if r["goal_first_correct"] and not r["degree_correct"]
    ]
    remaining_errors = [r for r in primary_rows if not r["goal_first_correct"]]
    salvaged_correct = [
        r for r in primary_rows if r["salvaged"] and r["goal_first_correct"]
    ]
    salvaged_error = [r for r in primary_rows if r["salvaged"] and not r["goal_first_correct"]]

    def compact_row(r: dict) -> dict:
        return {
            "record_id": r["record_id"],
            "gold_route": r["gold_route"],
            "goal_first": r["goal_first"],
            "degree": r["degree"],
            "goal_licensed": r["goal_licensed"],
            "rich": r["rich"],
            "t39_full": r.get("t39_full"),
            "speech_act": r["speech_act"],
            "capability_status": r["capability_status"],
            "pilot_capability": r["pilot_capability"],
            "risk_level": r["risk_level"],
            "live_matched_rule": r["live_matched_rule"],
            "salvaged": r["salvaged"],
            "intent_summary": (r.get("intent_summary") or "")[:180],
        }

    autopsy = {
        "replica": "R1",
        "note": "R2/R3 live routes already agree 120/120 with R1; autopsy uses R1 analyses.",
        "goal_first_errors": len(remaining_errors),
        "degree_only_correct_n": len(degree_only),
        "goal_first_only_correct_n": len(gf_only),
        "degree_only_correct_ids": [r["record_id"] for r in degree_only],
        "goal_first_only_correct_ids": [r["record_id"] for r in gf_only],
        "degree_only_by_gold": dict(Counter(r["gold_route"] for r in degree_only)),
        "degree_only_goal_first_pred": dict(Counter(r["goal_first"] for r in degree_only)),
        "degree_only_matched_rule": dict(Counter(r["live_matched_rule"] or "none" for r in degree_only)),
        "degree_only_pilot_capability": dict(
            Counter(r["pilot_capability"] or "none" for r in degree_only)
        ),
        "gf_only_by_gold": dict(Counter(r["gold_route"] for r in gf_only)),
        "gf_only_degree_pred": dict(Counter(r["degree"] for r in gf_only)),
        "remaining_error_ids": [r["record_id"] for r in remaining_errors],
        "remaining_errors_by_gold_to_pred": confusion_counts(
            [(r["gold_route"], r["goal_first"]) for r in remaining_errors]
        ),
        "salvage_ids": [r["record_id"] for r in primary_rows if r["salvaged"]],
        "salvage_correct_ids": [r["record_id"] for r in salvaged_correct],
        "salvage_error_ids": [r["record_id"] for r in salvaged_error],
        "salvage_correct_n": len(salvaged_correct),
        "salvage_error_n": len(salvaged_error),
        "salvage_in_degree_only": [
            r["record_id"] for r in degree_only if r["salvaged"]
        ],
        "degree_only_rows": [compact_row(r) for r in degree_only],
        "goal_first_only_rows": [compact_row(r) for r in gf_only],
        "salvage_rows": [compact_row(r) for r in primary_rows if r["salvaged"]],
    }

    # Exploratory intent_summary proxy (not official SGC).
    proxy_rows = []
    for r in primary_rows:
        g = intent[r["record_id"]]
        excerpt = (r.get("intent_summary") or "").strip()
        proxies = {
            str(t): proxy_pass(excerpt, g["reference_A_intent_text"], g["reference_B_intent_text"], t)
            for t in THRESHOLDS
        }
        proxy_rows.append(
            {
                "record_id": r["record_id"],
                "gold_route": r["gold_route"],
                "predicted_route": r["goal_first"],
                "route_correct": r["goal_first_correct"],
                "salvaged": r["salvaged"],
                "intent_summary": excerpt,
                "proxies": proxies,
            }
        )

    by_threshold = {}
    for t in THRESHOLDS:
        flags = [row["proxies"][str(t)]["proxy_correct"] for row in proxy_rows]
        overlaps = [row["proxies"][str(t)]["overlap_best"] for row in proxy_rows]
        empties = [row["proxies"][str(t)]["excerpt_empty"] for row in proxy_rows]
        conflicts = [row["proxies"][str(t)]["polarity_conflict"] for row in proxy_rows]
        summary = summarize_proxy(flags, overlaps, empties, conflicts)
        gold_exec_ok = sum(
            row["proxies"][str(t)]["proxy_correct"] and row["gold_route"] == "execute"
            for row in proxy_rows
        )
        route_and_proxy = sum(
            row["proxies"][str(t)]["proxy_correct"] and row["route_correct"] for row in proxy_rows
        )
        salvage_proxy = sum(
            row["proxies"][str(t)]["proxy_correct"] for row in proxy_rows if row["salvaged"]
        )
        summary.update(
            {
                "threshold": t,
                "proxy_correct_on_gold_execute": gold_exec_ok,
                "gold_execute_n": 76,
                "route_and_proxy_both": route_and_proxy,
                "salvage_proxy_correct": salvage_proxy,
            }
        )
        by_threshold[str(t)] = summary

    frozen_compare = None
    if frozen_base_proxy:
        primary = frozen_base_proxy.get("primary") or frozen_base_proxy.get("by_threshold", {}).get(
            str(PRIMARY_THRESHOLD), {}
        )
        frozen_compare = {
            "artifact": "outputs/base_vs_adapter_goal_trace_proxy_20260911.json",
            "claim_boundary": frozen_base_proxy.get("claim_boundary"),
            "threshold": PRIMARY_THRESHOLD,
            "direct_base_proxy_correct": primary.get("base_proxy_correct"),
            "adapter_proxy_correct_unofficial": primary.get("adapter_proxy_correct"),
            "v2_intent_summary_proxy_correct": by_threshold[str(PRIMARY_THRESHOLD)]["proxy_correct"],
        }

    proxy_report = {
        "analysis_id": "gfv2_intent_summary_goal_trace_proxy_20260912",
        "claim_boundary": (
            "Exploratory lexical/polarity proxy on v2 intent_summary only. "
            "NOT official SGC. Official SGC requires two prediction-blind LLM judges. "
            "Compared to frozen base/adapter think-trace proxy, not to leftover T39 SGC 113/120."
        ),
        "replica": "R1",
        "gold": str(INTENT_GOLD.relative_to(ROOT)).replace("\\", "/"),
        "predictions": "outputs/cluster_pulls/r1_manager/predictions/goal_first_manager_v2.predictions.jsonl",
        "primary_threshold": PRIMARY_THRESHOLD,
        "by_threshold": by_threshold,
        "primary": by_threshold[str(PRIMARY_THRESHOLD)],
        "vs_frozen_base_adapter_proxy": frozen_compare,
        "official_sgc_not_run": True,
        "gpu_judges_not_started": True,
    }

    r1 = licensed_by_replica["R1"]
    report = {
        "analysis_id": "gfv2_local_lane_a_20260912",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "claim_boundary": (
            "CPU reroute and proxy on salvaged v2 predictions. Salvage is post-rebuild, "
            "not clean first-pass JSON. T39/T41 frozen. Adapter unofficial. "
            "Do not pool natives with Pilot-120. Three natives still pending on 53420. "
            "Goal-licensed is a policy ablation, not a live GPU system. "
            "Intent-summary proxy is exploratory, not official SGC."
        ),
        "gold_sha256": gold_hash,
        "replicas_with_local_predictions": sorted(replicas),
        "replicas_evals_only": [
            name
            for name, path in (("R3", PULLS / "r3_manager"),)
            if name not in replicas and (path / "evaluations").exists()
        ],
        "licensed_policy": POLICY_GOAL_FIRST_V2_GOAL_LICENSED,
        "r1": replica_payload.get("R1"),
        "r2": replica_payload.get("R2"),
        "r3": replica_payload.get("R3"),
        "headline": {
            "goal_first_live": r1["goal_first"]["n_correct"],
            "goal_licensed": r1["goal_licensed"]["n_correct"],
            "degree": r1["degree"]["n_correct"],
            "rich": r1["rich"]["n_correct"],
            "blind": r1["blind"]["n_correct"],
            "t39_full_manager_frozen": 33,
            "direct_base_frozen": 88,
            "adapter_unofficial_frozen": 87,
            "false_execute_on_gold_refuse": {
                "goal_first": r1["goal_first"]["false_execute_on_gold_refuse"],
                "goal_licensed": r1["goal_licensed"]["false_execute_on_gold_refuse"],
                "degree": r1["degree"]["false_execute_on_gold_refuse"],
                "rich": r1["rich"]["false_execute_on_gold_refuse"],
                "blind": r1["blind"]["false_execute_on_gold_refuse"],
            },
            "licensed_route_flips_vs_live": r1["licensed_minus_live"]["n_route_flips"],
        },
        "error_autopsy": autopsy,
        "proxy_primary": proxy_report["primary"],
        "proxy_vs_frozen_base_adapter": frozen_compare,
        "still_pending": ["gemma4/indirect", "glm47/ambik", "glm47/indirect"],
        "retry_job": "53420",
    }

    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUT_SUMMARY.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with OUT_ROWS.open("w", encoding="utf-8", newline="\n") as handle:
        for row in primary_rows:
            slim = {k: v for k, v in row.items() if k != "licensed_notes"}
            handle.write(json.dumps(slim, ensure_ascii=False, sort_keys=True) + "\n")
    OUT_PROXY.write_text(json.dumps(proxy_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with OUT_PROXY_ROWS.open("w", encoding="utf-8", newline="\n") as handle:
        for row in proxy_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    print(
        json.dumps(
            {
                "summary": str(OUT_SUMMARY.relative_to(ROOT)).replace("\\", "/"),
                "headline": report["headline"],
                "replicas": sorted(replicas),
                "licensed_flips": r1["licensed_minus_live"]["n_route_flips"],
                "autopsy_degree_only": autopsy["degree_only_correct_n"],
                "proxy_primary": proxy_report["primary"]["proxy_correct"],
                "rebuilt_match_r1": r1["rebuilt_v2_matches_live"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
