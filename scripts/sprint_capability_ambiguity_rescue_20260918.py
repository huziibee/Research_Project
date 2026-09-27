#!/usr/bin/env python3
"""Sprint rescue: capability calibration deltas + ambiguity vocab audit.

CPU-only. Reuses frozen T0.7 predictions and optional LLM judgments.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ambiguity_manager.evaluation import pilot_120 as p120  # noqa: E402
from lib_capability_debate_20260918 import (  # noqa: E402
    CAPABILITY_SET,
    analysis_dict_from_pred,
    analysis_from_dict,
    load_jsonl_by_id,
    norm_route,
    patch_capability_in_analysis,
    prior_capability_from_pred,
    route_from_analysis,
)

# Intent automatic-overlap helpers (same family as dig playbook).
_CONTENT_RE = re.compile(r"[a-z0-9]+", re.I)


def content_tokens(text: str) -> set[str]:
    return {t.lower() for t in _CONTENT_RE.findall(text or "") if len(t) > 1}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


_NEG = {"not", "no", "never", "dont", "don't", "cannot", "cant", "can't", "refuse", "forbidden"}


def polarity_flip(pred: str, ref: str) -> bool:
    pt, rt = content_tokens(pred), content_tokens(ref)
    pn, rn = bool(pt & _NEG), bool(rt & _NEG)
    return pn != rn and bool(pt & rt)


def intent_pass(pred_summary: str, gold: dict[str, Any], thr: float = 0.18) -> bool:
    refs = [
        str(gold.get("reference_A_intent_text") or ""),
        str(gold.get("reference_B_intent_text") or ""),
    ]
    pt = content_tokens(pred_summary)
    best = 0.0
    for ref in refs:
        if not ref.strip():
            continue
        score = jaccard(pt, content_tokens(ref))
        if polarity_flip(pred_summary, ref):
            continue
        best = max(best, score)
    return best >= thr


def pilot17() -> set[str]:
    try:
        from ambiguity_manager.systems.goal_first_analysis_v2 import AMBIGUITY_TYPES

        return set(AMBIGUITY_TYPES)
    except Exception:
        pass
    for attr in ("PILOT_17_AMBIGUITY_TYPES", "AMBIGUITY_TYPES_PILOT_17", "PILOT_AMBIGUITY_TYPES"):
        if hasattr(p120, attr):
            return {str(x) for x in getattr(p120, attr)}
    return set()


def gold_ambiguity_set(g: dict[str, Any]) -> set[str]:
    raw = g.get("ambiguity_types") or g.get("gold_ambiguity_types") or []
    if isinstance(raw, str):
        return {raw} if raw else set()
    return {str(x) for x in raw}


def pred_ambiguity_set(pred: dict[str, Any]) -> set[str]:
    # Prefer Pilot-17 scored field on the prediction row (not coarse analysis.ambiguity_types).
    raw = pred.get("ambiguity_types")
    if isinstance(raw, list) and raw:
        return {str(x) for x in raw}
    analysis = analysis_dict_from_pred(pred) or {}
    for finding in analysis.get("findings") or []:
        text = str(finding)
        if text.startswith("pilot_ambiguity_types:"):
            try:
                payload = json.loads(text.split(":", 1)[1])
                if isinstance(payload, list):
                    return {str(x) for x in payload}
            except json.JSONDecodeError:
                pass
    raw = analysis.get("ambiguity_types") or []
    if isinstance(raw, str):
        return {raw} if raw else set()
    out: set[str] = set()
    for x in raw:
        if isinstance(x, dict):
            out.add(str(x.get("type") or x.get("name") or x))
        else:
            out.add(str(x))
    return out


def soft_f1(pred: set[str], gold: set[str]) -> float:
    if not pred and not gold:
        return 1.0
    if not pred or not gold:
        return 0.0
    tp = len(pred & gold)
    if tp == 0:
        return 0.0
    p = tp / len(pred)
    r = tp / len(gold)
    return 2 * p * r / (p + r)


def coerce_to_vocab(tags: set[str], vocab: set[str]) -> set[str]:
    return {t for t in tags if t in vocab}


def route_correct(pred_route: str, gold_route: str) -> bool:
    return norm_route(pred_route) == norm_route(gold_route)


def score_routes(
    preds: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    *,
    judgments: dict[str, dict[str, Any]] | None = None,
    oracle_gold: bool = False,
    use_emitted_route: bool = False,
    system: str = "goal_first_manager_v2",
) -> dict[str, Any]:
    n_correct = 0
    false_refuse = 0
    dissociation = []  # intent yes, route no
    cap_match = 0
    details = []
    for rid in sorted(preds):
        pred = preds[rid]
        g = gold[rid]
        gold_route = norm_route(str(g.get("terminal_strategy")))
        gold_cap = str(g.get("capability_status"))
        analysis0 = analysis_dict_from_pred(pred)
        summary = ""
        if analysis0 is not None:
            summary = str(analysis0.get("intent_summary") or "")
        if not summary:
            summary = str(pred.get("intent_summary") or "")

        if use_emitted_route or analysis0 is None:
            live = norm_route(str(pred.get("terminal_strategy") or "")) or "missing"
            prior_cap = prior_capability_from_pred(pred) if analysis0 else None
            new_cap = prior_cap
            ip = intent_pass(summary, g)
            ok = route_correct(live, gold_route)
            n_correct += int(ok)
            if gold_route == "execute" and live == "refuse":
                false_refuse += 1
            if ip and not ok:
                dissociation.append(rid)
            if new_cap == gold_cap:
                cap_match += 1
            details.append(
                {
                    "record_id": rid,
                    "route": live,
                    "gold_route": gold_route,
                    "intent_pass": ip,
                    "emitted": True,
                    "skipped": analysis0 is None,
                }
            )
            continue

        prior_cap = prior_capability_from_pred(pred)
        if oracle_gold:
            new_cap = gold_cap
            patched = patch_capability_in_analysis(analysis0, new_cap)
        elif judgments is not None:
            j = judgments.get(rid)
            if j is None or j.get("failed") or not j.get("capability_status"):
                new_cap = prior_cap if prior_cap in CAPABILITY_SET else "capable"
            else:
                new_cap = str(j["capability_status"])
            patched = patch_capability_in_analysis(analysis0, new_cap)
        else:
            new_cap = prior_cap
            patched = analysis0

        routes = route_from_analysis(analysis_from_dict(patched))
        live = routes[system]
        summary = str(patched.get("intent_summary") or summary)
        ip = intent_pass(summary, g)
        ok = route_correct(live, gold_route)
        n_correct += int(ok)
        if gold_route == "execute" and live == "refuse":
            false_refuse += 1
        if ip and not ok:
            dissociation.append(rid)
        if new_cap == gold_cap:
            cap_match += 1
        details.append(
            {
                "record_id": rid,
                "route": live,
                "gold_route": gold_route,
                "intent_pass": ip,
                "capability": new_cap,
                "gold_capability": gold_cap,
                "prior_capability": prior_cap,
            }
        )
    return {
        "n": 120,
        "n_correct": n_correct,
        "accuracy": n_correct / 120,
        "false_refuse_on_gold_execute": false_refuse,
        "capability_accuracy": cap_match / 120,
        "dissociation_n": len(dissociation),
        "dissociation_ids": dissociation,
        "_route_ok": {d["record_id"]: route_correct(d["route"], d["gold_route"]) for d in details},
    }


def ambiguity_audit(
    preds: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    vocab: set[str],
) -> dict[str, Any]:
    exact = 0
    soft_sum = 0.0
    soft_coerced_sum = 0.0
    exact_coerced = 0
    tag_counts: Counter[str] = Counter()
    oov_counts: Counter[str] = Counter()
    per_type = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    n_pred_tags = 0
    n_oov_tags = 0
    empty_pred = 0
    for rid in sorted(preds):
        gset = gold_ambiguity_set(gold[rid])
        pset = pred_ambiguity_set(preds[rid])
        if not pset:
            empty_pred += 1
        for t in pset:
            tag_counts[t] += 1
            n_pred_tags += 1
            if t not in vocab:
                oov_counts[t] += 1
                n_oov_tags += 1
        if pset == gset:
            exact += 1
        soft_sum += soft_f1(pset, gset)
        cset = coerce_to_vocab(pset, vocab)
        if cset == gset:
            exact_coerced += 1
        soft_coerced_sum += soft_f1(cset, gset)
        for t in vocab:
            in_p = t in pset
            in_g = t in gset
            if in_p and in_g:
                per_type[t]["tp"] += 1
            elif in_p and not in_g:
                per_type[t]["fp"] += 1
            elif in_g and not in_p:
                per_type[t]["fn"] += 1

    type_pr: dict[str, Any] = {}
    for t, c in sorted(per_type.items()):
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        type_pr[t] = {"precision": p, "recall": r, "f1": f1, **c}

    in_vocab_rate = 1.0 - (n_oov_tags / n_pred_tags) if n_pred_tags else 1.0
    return {
        "n": 120,
        "exact_set": exact,
        "exact_set_rate": exact / 120,
        "soft_f1_mean": soft_sum / 120,
        "exact_set_after_vocab_coerce": exact_coerced,
        "soft_f1_mean_after_vocab_coerce": soft_coerced_sum / 120,
        "empty_pred_bags": empty_pred,
        "n_pred_tag_instances": n_pred_tags,
        "n_oov_tag_instances": n_oov_tags,
        "in_vocab_instance_rate": in_vocab_rate,
        "top_predicted_tags": tag_counts.most_common(20),
        "top_oov_tags": oov_counts.most_common(20),
        "per_type": type_pr,
        "vocab_size": len(vocab),
        "vocab": sorted(vocab),
    }


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--predictions", type=Path, required=True)
    ap.add_argument("--judgments", type=Path, default=None)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--lane-rows", type=Path, default=None)
    args = ap.parse_args()

    root = args.root.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    gold = load_jsonl_by_id(root / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl")
    intent_gold_path = (
        root
        / "pilot120_intent_evaluation_20260902"
        / "pilot120_intent_evaluation_20260902"
        / "validation"
        / "self_contained_rebuild"
        / "data"
        / "intent_gold_references_120.jsonl"
    )
    if intent_gold_path.exists():
        intent_gold = load_jsonl_by_id(intent_gold_path)
        for rid, g in gold.items():
            ig = intent_gold.get(rid) or {}
            g.setdefault("reference_A_intent_text", ig.get("reference_A_intent_text"))
            g.setdefault("reference_B_intent_text", ig.get("reference_B_intent_text"))
    preds = load_jsonl_by_id(args.predictions.resolve())
    judgments = load_jsonl_by_id(args.judgments.resolve()) if args.judgments else {}

    if len(preds) != 120 or set(preds) != set(gold):
        raise SystemExit(f"id_mismatch n={len(preds)}")

    # Emit-time routes = pre code-fix baseline; then current routing.py variants.
    emit_baseline = score_routes(preds, gold, use_emitted_route=True)
    codefix_only = score_routes(preds, gold)  # frozen caps, fixed unauthorized gate
    oracle = score_routes(preds, gold, oracle_gold=True)
    llm = score_routes(preds, gold, judgments=judgments) if judgments else None
    baseline = emit_baseline

    # Historical 62-slab from T0 matched intent-yes ∩ route-no when provided.
    hist_slab: list[str] = []
    if args.lane_rows and args.lane_rows.exists():
        path = args.lane_rows
        if path.suffix == ".json":
            obj = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(obj, dict) and "ids" in obj:
                hist_slab = [str(x) for x in obj["ids"]]
            elif isinstance(obj, list):
                hist_slab = [str(x) for x in obj]
        else:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                # Proxy rows: intent @0.18 pass and route incorrect.
                proxies = row.get("proxies") or {}
                p018 = proxies.get("0.18") if isinstance(proxies, dict) else None
                if isinstance(p018, dict) and p018.get("proxy_correct") and not row.get(
                    "route_correct", True
                ):
                    hist_slab.append(str(row["record_id"]))
                elif row.get("intent_yes") and not row.get("routing_correct"):
                    hist_slab.append(str(row["record_id"]))

    # Prefer historical 62 for rescue deltas when available; else recompute on emit.
    if hist_slab:
        slab62 = sorted(set(hist_slab))
        slab_source = f"historical_file:{args.lane_rows}"
    else:
        slab62 = emit_baseline["dissociation_ids"]
        slab_source = "recomputed_intent_yes_route_no_on_emit_baseline"

    def slab_rescue(score: dict[str, Any], *, relative_to: dict[str, Any] | None = None) -> dict[str, Any]:
        # Among historical intent-yes/route-no IDs that are still wrong on relative_to
        # (default: emit baseline), how many become route-correct under score.
        base = relative_to or emit_baseline
        eligible = [
            rid
            for rid in slab62
            if base.get("_route_ok", {}).get(rid) is False
        ]
        rescued = [rid for rid in eligible if score.get("_route_ok", {}).get(rid) is True]
        still = [rid for rid in eligible if rid not in rescued]
        already_ok_on_base = [
            rid for rid in slab62 if base.get("_route_ok", {}).get(rid) is True
        ]
        return {
            "historical_slab_n": len(slab62),
            "still_wrong_on_baseline": len(eligible),
            "already_correct_on_baseline": len(already_ok_on_base),
            "rescued_to_correct_route": len(rescued),
            "still_wrong_route": len(still),
            "rescued_ids": rescued,
            "still_ids": still,
        }

    amb = ambiguity_audit(preds, gold, pilot17())

    report = {
        "predictions": str(args.predictions).replace("\\", "/"),
        "judgments": None if not args.judgments else str(args.judgments).replace("\\", "/"),
        "routing_code_note": (
            "emit_baseline uses prediction terminal_strategy (pre-fix router). "
            "codefix_only / oracle / llm re-route via current routing.py "
            "(unauthorized refuses only at elevated risk)."
        ),
        "emit_baseline_pre_codefix": emit_baseline,
        "codefix_only_frozen_capability": codefix_only,
        "oracle_gold_capability_current_router": oracle,
        "llm_patch_capability_current_router": llm,
        "dissociation_slab": {
            "source": slab_source,
            "n": len(slab62),
            "ids": slab62,
            "rescue_under_codefix": slab_rescue(codefix_only),
            "rescue_under_oracle": slab_rescue(oracle),
            "rescue_under_llm": slab_rescue(llm) if llm else None,
        },
        "historical_lane_a_ids": {
            "n": len(hist_slab),
            "ids": hist_slab,
            "overlap_with_emit_dissociation": len(
                set(hist_slab) & set(emit_baseline["dissociation_ids"])
            ),
        },
        "ambiguity": amb,
        "headline": {
            "gf_emit_baseline": f"{emit_baseline['n_correct']}/120",
            "gf_codefix_only": f"{codefix_only['n_correct']}/120",
            "gf_oracle": f"{oracle['n_correct']}/120",
            "gf_llm": None if llm is None else f"{llm['n_correct']}/120",
            "false_refuse_emit": emit_baseline["false_refuse_on_gold_execute"],
            "false_refuse_codefix": codefix_only["false_refuse_on_gold_execute"],
            "false_refuse_oracle": oracle["false_refuse_on_gold_execute"],
            "false_refuse_llm": None if llm is None else llm["false_refuse_on_gold_execute"],
            "dissociation_emit": emit_baseline["dissociation_n"],
            "dissociation_codefix": codefix_only["dissociation_n"],
            "dissociation_oracle": oracle["dissociation_n"],
            "dissociation_llm": None if llm is None else llm["dissociation_n"],
            "ambiguity_exact": amb["exact_set"],
            "ambiguity_soft_f1": amb["soft_f1_mean"],
            "ambiguity_in_vocab_rate": amb["in_vocab_instance_rate"],
            "ambiguity_exact_after_coerce": amb["exact_set_after_vocab_coerce"],
            "ambiguity_soft_f1_after_coerce": amb["soft_f1_mean_after_vocab_coerce"],
        },
    }
    write_json(out / "sprint_rescue_summary.json", report)
    write_json(out / "ambiguity_audit.json", amb)
    print(json.dumps(report["headline"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
