#!/usr/bin/env python3
"""Exploratory goal-trace proxy: direct_base vs provisional adapter on Pilot-120.

NOT official SGC. Official SGC needs two prediction-blind LLM judges under the
frozen protocol. This reuses the same gold-independent trace cleaning and
intent-excerpt extraction, then scores a transparent lexical/polarity proxy so
we have evidence before a full judge run.

Claim boundary: observable cleaned think-trace recovery vs two pre-T39 intent
references. Route correctness is reported only as context.
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pilot120_intent_evaluation_20260902" / "pilot120_intent_evaluation_20260902" / "scripts"))
from intent_eval_common import (  # type: ignore
    clean_observable_trace,
    exact_mcnemar_p,
    extract_intent_candidate_text,
    paired_bootstrap_difference,
    wilson_interval,
)

STOP = {
    "a", "an", "the", "to", "of", "and", "or", "for", "in", "on", "at", "by", "with",
    "from", "into", "is", "are", "be", "been", "being", "that", "this", "it", "as",
    "user", "wants", "want", "should", "must", "please", "can", "could", "would",
    "robot", "command", "task", "then", "after", "before", "their", "its", "them",
}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def by_id(rows: list[dict]) -> dict[str, dict]:
    out = {}
    for row in rows:
        rid = row["record_id"]
        if rid in out:
            raise SystemExit(f"duplicate:{path_hint}:{rid}")
        out[rid] = row
    return out


path_hint = ""


def content_tokens(text: str) -> set[str]:
    toks = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {t for t in toks if t not in STOP and len(t) > 2}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


NEG_RE = re.compile(r"\b(do not|don't|dont|never|prohibit|avoid|refrain|no longer)\b", re.I)


def polarity_conflict(cand: str, gold: str) -> bool:
    return bool(NEG_RE.search(cand)) != bool(NEG_RE.search(gold))


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
    # Proxy "understood": nonempty excerpt, no polarity flip vs best gold, overlap >= threshold
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


def route_correct(pred: str | None, gold: str | None) -> bool:
    def norm(x: str | None) -> str:
        x = (x or "").strip().lower()
        if x in {"face_preserving_rejection", "reject", "refuse", "rejection"}:
            return "refuse"
        if x in {"clarify", "clarification"}:
            return "clarify"
        if x in {"execute", "act"}:
            return "execute"
        return x

    return norm(pred) == norm(gold) and bool(norm(gold))


def main() -> None:
    gold_path = ROOT / "pilot120_intent_evaluation_20260902/pilot120_intent_evaluation_20260902/data/intent_gold_references_120.jsonl"
    review = ROOT / "review_bundles/pilot120_t39_20260902/cluster_outputs/R1"
    gold = by_id(load_jsonl(gold_path))

    gold_routes: dict[str, str] = {}
    gold_route_paths = [
        ROOT / "review_bundles/pilot120_t39_20260902/frozen_inference_source_6d71aff/data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl",
        ROOT / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl",
    ]
    for gp in gold_route_paths:
        if not gp.exists():
            continue
        for row in load_jsonl(gp):
            rid = row.get("record_id")
            route = row.get("terminal_strategy")
            if rid and route:
                gold_routes[rid] = route
        break

    systems = {
        "direct_base_llm": review / "direct_base/direct_base_llm.predictions.jsonl",
        "t28_selected_adapter_llm": review / "selected_adapter/t28_selected_adapter_llm.predictions.jsonl",
    }
    preds = {name: by_id(load_jsonl(path)) for name, path in systems.items()}
    ids = sorted(gold)
    if set(preds["direct_base_llm"]) != set(ids) or set(preds["t28_selected_adapter_llm"]) != set(ids):
        raise SystemExit("id_binding_failed")

    thresholds = [0.12, 0.18, 0.25]
    rows_out = []
    for rid in ids:
        g = gold[rid]
        cmd = (g.get("source") or {}).get("command") or ""
        # gold file may embed source; if not, recover from reference packet
        if not cmd:
            # intent gold references include source in build; check keys
            pass
        item = {"record_id": rid, "gold_route": gold_routes.get(rid), "systems": {}}
        for name, table in preds.items():
            raw = table[rid].get("raw_output") or ""
            # Prefer command from source_canonical if gold lacks it
            source_cmd = cmd
            clean = clean_observable_trace(raw, source_command=source_cmd)
            excerpt = extract_intent_candidate_text(raw, source_command=source_cmd)
            pred_route = table[rid].get("terminal_strategy")
            sys_row = {
                "raw_output_sha256": __import__("hashlib").sha256(raw.encode()).hexdigest(),
                "cleaned_chars": len(clean),
                "intent_excerpt": excerpt,
                "predicted_route": pred_route,
                "route_correct": route_correct(pred_route, gold_routes.get(rid)) if rid in gold_routes else None,
                "proxies": {
                    str(t): proxy_pass(excerpt, g["reference_A_intent_text"], g["reference_B_intent_text"], t)
                    for t in thresholds
                },
            }
            item["systems"][name] = sys_row
        rows_out.append(item)

    # If source commands missing from gold file, reload gold with source from source_canonical
    src_path = ROOT / "pilot120_intent_evaluation_20260902/pilot120_intent_evaluation_20260902/evidence/closure_snapshot/reference/source_canonical.jsonl"
    if src_path.exists() and not (gold[ids[0]].get("source") or {}).get("command"):
        src = by_id(load_jsonl(src_path))
        rows_out = []
        for rid in ids:
            g = gold[rid]
            cmd = src[rid].get("command") or ""
            item = {"record_id": rid, "gold_route": gold_routes.get(rid), "source_command": cmd, "systems": {}}
            for name, table in preds.items():
                raw = table[rid].get("raw_output") or ""
                clean = clean_observable_trace(raw, source_command=cmd)
                excerpt = extract_intent_candidate_text(raw, source_command=cmd)
                pred_route = table[rid].get("terminal_strategy")
                item["systems"][name] = {
                    "raw_output_sha256": __import__("hashlib").sha256(raw.encode()).hexdigest(),
                    "cleaned_chars": len(clean),
                    "intent_excerpt": excerpt,
                    "predicted_route": pred_route,
                    "route_correct": route_correct(pred_route, gold_routes.get(rid)) if rid in gold_routes else None,
                    "proxies": {
                        str(t): proxy_pass(excerpt, g["reference_A_intent_text"], g["reference_B_intent_text"], t)
                        for t in thresholds
                    },
                }
            rows_out.append(item)

    def summarize(threshold: float) -> dict:
        t = str(threshold)
        base = [r["systems"]["direct_base_llm"]["proxies"][t]["proxy_correct"] for r in rows_out]
        adp = [r["systems"]["t28_selected_adapter_llm"]["proxies"][t]["proxy_correct"] for r in rows_out]
        base_ov = [r["systems"]["direct_base_llm"]["proxies"][t]["overlap_best"] for r in rows_out]
        adp_ov = [r["systems"]["t28_selected_adapter_llm"]["proxies"][t]["overlap_best"] for r in rows_out]
        n01 = sum((not b) and a for b, a in zip(base, adp))  # adapter only
        n10 = sum(b and (not a) for b, a in zip(base, adp))  # base only
        br = [r["systems"]["direct_base_llm"]["route_correct"] for r in rows_out]
        ar = [r["systems"]["t28_selected_adapter_llm"]["route_correct"] for r in rows_out]
        return {
            "threshold": threshold,
            "n": len(rows_out),
            "base_proxy_correct": sum(base),
            "adapter_proxy_correct": sum(adp),
            "base_proxy_rate": sum(base) / len(base),
            "adapter_proxy_rate": sum(adp) / len(adp),
            "base_wilson95": wilson_interval(sum(base), len(base)),
            "adapter_wilson95": wilson_interval(sum(adp), len(adp)),
            "mean_overlap_base": sum(base_ov) / len(base_ov),
            "mean_overlap_adapter": sum(adp_ov) / len(adp_ov),
            "adapter_only_proxy_wins": n01,
            "base_only_proxy_wins": n10,
            "both_proxy": sum(b and a for b, a in zip(base, adp)),
            "neither_proxy": sum((not b) and (not a) for b, a in zip(base, adp)),
            "mcnemar_exact_p": exact_mcnemar_p(n01, n10),
            "paired_bootstrap_adapter_minus_base": paired_bootstrap_difference(adp, base, reps=5000, seed=20260911),
            "base_route_correct": sum(x for x in br if x is not None),
            "adapter_route_correct": sum(x for x in ar if x is not None),
            "base_empty_excerpts": sum(r["systems"]["direct_base_llm"]["proxies"][t]["excerpt_empty"] for r in rows_out),
            "adapter_empty_excerpts": sum(r["systems"]["t28_selected_adapter_llm"]["proxies"][t]["excerpt_empty"] for r in rows_out),
            "base_polarity_conflicts": sum(r["systems"]["direct_base_llm"]["proxies"][t]["polarity_conflict"] for r in rows_out),
            "adapter_polarity_conflicts": sum(r["systems"]["t28_selected_adapter_llm"]["proxies"][t]["polarity_conflict"] for r in rows_out),
        }

    primary = summarize(0.18)
    report = {
        "analysis_id": "base_vs_adapter_goal_trace_proxy_20260911",
        "claim_boundary": (
            "Exploratory lexical/polarity proxy on cleaned observable think-traces. "
            "NOT official SGC. Official SGC requires two prediction-blind judges."
        ),
        "inputs": {
            "gold": str(gold_path.relative_to(ROOT)),
            "base_predictions": "review_bundles/pilot120_t39_20260902/cluster_outputs/R1/direct_base/direct_base_llm.predictions.jsonl",
            "adapter_predictions": "review_bundles/pilot120_t39_20260902/cluster_outputs/R1/selected_adapter/t28_selected_adapter_llm.predictions.jsonl",
            "trace_cleaner": "pilot120_intent_evaluation_20260902/.../intent_eval_common.py",
        },
        "primary_threshold": 0.18,
        "by_threshold": {str(t): summarize(t) for t in thresholds},
        "primary": primary,
        "verdict": (
            "adapter_better"
            if primary["adapter_proxy_correct"] > primary["base_proxy_correct"]
            else "base_better_or_tie"
            if primary["adapter_proxy_correct"] < primary["base_proxy_correct"]
            else "tie"
        ),
    }

    out_dir = ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)
    detail = out_dir / "base_vs_adapter_goal_trace_proxy_rows_20260911.jsonl"
    with detail.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows_out:
            # keep excerpts but not full raw
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    summary_path = out_dir / "base_vs_adapter_goal_trace_proxy_20260911.json"
    summary_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"summary": str(summary_path), "detail": str(detail), "primary": primary, "verdict": report["verdict"]}, indent=2))


if __name__ == "__main__":
    main()
