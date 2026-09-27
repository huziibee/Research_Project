#!/usr/bin/env python3
"""Row-level diagnosis of official wording 0/23 and CPC F1 0.045.

Does not mutate gold. Writes a JSON report for inspection.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from score_official_sidecar_followon import (  # noqa: E402
    OFFICIAL_CPC,
    OFFICIAL_WORDING,
    STOP,
    _first,
    _item_covered,
    _tokens,
)
from score_pilot120_cpc_and_risk import load_jsonl, normalize_prediction  # noqa: E402
from ambiguity_manager.evaluation.evaluator import DeterministicEvaluator  # noqa: E402
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES  # noqa: E402

PRED = {
    "goal_first": ROOT / "outputs/cluster_pulls/r1_manager/predictions/goal_first_manager_v2.predictions.jsonl",
    "degree": ROOT / "outputs/cluster_pulls/r1_manager/predictions/degree_based_router_v2.predictions.jsonl",
    "timid": ROOT / "outputs/cluster_pulls/r1_manager/predictions/rich_conservative_manager_v2.predictions.jsonl",
    "context_blind": ROOT / "outputs/cluster_pulls/r1_manager/predictions/goal_first_context_blind_v2.predictions.jsonl",
    "raw_qwen": ROOT / "outputs/t45_historical_reconciliation_local_20260901/inputs/direct_base_llm.predictions.jsonl",
    "fine_tune": ROOT / "outputs/t45_historical_reconciliation_local_20260901/inputs/t28_selected_adapter_llm.predictions.jsonl",
}


def question_fields(row: dict) -> dict:
    parsed = row.get("parsed") if isinstance(row.get("parsed"), dict) else {}
    analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
    return {
        "top_q": row.get("clarification_question"),
        "parsed_q": parsed.get("clarification_question"),
        "analysis_q": analysis.get("clarification_question"),
        "unresolved": analysis.get("unresolved_slots") or parsed.get("unresolved_slots"),
        "targets": _first(
            row.get("clarification_targets"),
            parsed.get("clarification_targets"),
            analysis.get("clarification_targets"),
            [],
        )
        or [],
        "route": _first(
            row.get("terminal_strategy"),
            parsed.get("terminal_strategy"),
            parsed.get("recommended_strategy"),
        ),
        "intent_summary": _first(row.get("intent_summary"), analysis.get("intent_summary"), parsed.get("intent_summary")),
        "raw_has_question_mark": "?" in str(row.get("raw_output") or ""),
        "raw_len": len(str(row.get("raw_output") or "")),
    }


def item_diag(item: str, blob_tokens: set[str], shared: set[str]) -> dict:
    toks = _tokens(item)
    distinctive = toks - shared or toks
    hit = distinctive & blob_tokens
    need = 1 if len(distinctive) <= 2 else 2
    if len(distinctive) == 1:
        need = 1
    return {
        "item": item,
        "tokens": sorted(toks),
        "distinctive": sorted(distinctive),
        "hit": sorted(hit),
        "need": need,
        "covered": _item_covered(item, blob_tokens, shared),
    }


def wording_rows() -> list[dict]:
    gold = load_jsonl(OFFICIAL_WORDING)
    preds = {name: load_jsonl(path) for name, path in PRED.items() if path.exists()}
    out = []
    for rid, grow in sorted(gold.items()):
        clar = grow["gold_clarification"]
        items = clar["wording_criteria"]["must_convey"]
        token_sets = [_tokens(x) for x in items]
        shared = set.intersection(*token_sets) if token_sets else set()
        systems = {}
        for name, rows in preds.items():
            fields = question_fields(rows.get(rid) or {})
            q = _first(fields["top_q"], fields["parsed_q"], fields["analysis_q"])
            blob = _tokens(str(q)) if q else set()
            per = [item_diag(item, blob, shared) for item in items]
            n_covered = sum(1 for p in per if p["covered"])
            systems[name] = {
                **{k: fields[k] for k in ("route", "targets", "intent_summary", "raw_has_question_mark")},
                "question": q,
                "n_must": len(items),
                "n_covered": n_covered,
                "all_covered": bool(q) and n_covered == len(items),
                "any_covered": n_covered > 0,
                "per_item": per,
                "gold_targets": clar["targets"],
                "target_subset": set(clar["targets"]).issubset(set(fields["targets"] or [])),
            }
        out.append(
            {
                "record_id": rid,
                "gold_targets": clar["targets"],
                "must_convey": items,
                "shared_tokens": sorted(shared),
                "systems": systems,
            }
        )
    return out


def cpc_diag() -> dict:
    gold = load_jsonl(OFFICIAL_CPC)
    pred_path = PRED["goal_first"]
    raw = load_jsonl(pred_path)
    norm = {rid: normalize_prediction(row) for rid, row in raw.items()}
    ev = DeterministicEvaluator()
    rules = ev.norm.get("rules", {})

    status_counter = Counter()
    pred_status = Counter()
    gold_filled_n = 0
    pred_filled_n = 0
    tp = fp = fn_omit = fn_wrong = 0
    near = []  # gold filled, pred filled, not equal, but token overlap
    omit_examples = []
    wrong_examples = []
    tp_examples = []
    filled_row_ids = []
    slot_tp = Counter()
    slot_fn_omit = Counter()
    slot_fn_wrong = Counter()
    slot_fp = Counter()
    slot_gold = Counter()

    def extract(cpc):
        return ev._extract_filled_cpc(cpc if isinstance(cpc, dict) else {}, {}, rules)[0]

    for rid, grow in gold.items():
        g = grow.get("gold_cpc") or {}
        p = (norm.get(rid) or {}).get("cpc") or {}
        g_fill = extract(g)
        p_fill = extract(p)
        gold_filled_n += len(g_fill)
        pred_filled_n += len(p_fill)
        if p_fill:
            filled_row_ids.append(rid)
        for slot, cell in g.items() if isinstance(g, dict) else []:
            if isinstance(cell, dict):
                status_counter[f"gold:{cell.get('status')}"] += 1
        for slot, cell in p.items() if isinstance(p, dict) else []:
            if isinstance(cell, dict):
                pred_status[str(cell.get("status"))] += 1
            elif cell in (None, "", {}, []):
                pred_status["empty"] += 1
            else:
                pred_status["scalar"] += 1
        for slot in set(g_fill) | set(p_fill):
            gv, pv = g_fill.get(slot), p_fill.get(slot)
            if gv is not None:
                slot_gold[slot] += 1
            if gv is not None and pv == gv:
                tp += 1
                slot_tp[slot] += 1
                if len(tp_examples) < 25:
                    tp_examples.append({"record_id": rid, "slot": slot, "value": gv})
            elif gv is not None and pv is None:
                fn_omit += 1
                slot_fn_omit[slot] += 1
                if len(omit_examples) < 15:
                    omit_examples.append({"record_id": rid, "slot": slot, "gold": gv, "pred_cell": p.get(slot)})
            elif gv is not None and pv is not None and pv != gv:
                fn_wrong += 1
                tp_as_fp = 1
                fp += 1
                slot_fn_wrong[slot] += 1
                gtoks = _tokens(str(gv))
                ptoks = _tokens(str(pv))
                overlap = sorted(gtoks & ptoks)
                rec = {
                    "record_id": rid,
                    "slot": slot,
                    "gold": gv,
                    "pred": pv,
                    "token_overlap": overlap,
                    "jaccard": (len(gtoks & ptoks) / len(gtoks | ptoks)) if (gtoks or ptoks) else 0,
                }
                wrong_examples.append(rec)
                if overlap:
                    near.append(rec)
            elif gv is None and pv is not None:
                fp += 1
                slot_fp[slot] += 1

    # Where does CPC live in raw pred vs normalized?
    loc = Counter()
    sample_raw_cpc = None
    for rid, row in list(raw.items())[:5]:
        parsed = row.get("parsed") if isinstance(row.get("parsed"), dict) else {}
        analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
        if row.get("cpc"):
            loc["top.cpc"] += 1
        if parsed.get("cpc"):
            loc["parsed.cpc"] += 1
        if analysis.get("cpc"):
            loc["parsed.analysis.cpc"] += 1
        if sample_raw_cpc is None and analysis.get("cpc"):
            sample_raw_cpc = {"record_id": rid, "cpc": analysis.get("cpc")}

    # Soft match: token-jaccard >= 0.5 on filled-vs-filled
    soft_tp = 0
    for rec in wrong_examples:
        if rec["jaccard"] >= 0.5:
            soft_tp += 1

    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn_omit + fn_wrong) if (tp + fn_omit + fn_wrong) else None
    f1 = None if prec is None or rec is None or prec + rec == 0 else 2 * prec * rec / (prec + rec)

    return {
        "gold_filled_cells": gold_filled_n,
        "pred_filled_cells": pred_filled_n,
        "pred_rows_with_any_fill": filled_row_ids,
        "n_rows_with_any_fill": len(filled_row_ids),
        "gold_status": dict(status_counter),
        "pred_status": dict(pred_status),
        "cpc_location_in_first_5": dict(loc),
        "micro": {
            "tp": tp,
            "fp": fp,
            "fn_omit": fn_omit,
            "fn_wrong_value": fn_wrong,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "if_wrong_values_counted_tp_at_jaccard_0.5": {
                "extra_tp": soft_tp,
                "tp_then": tp + soft_tp,
                "fn_wrong_then": fn_wrong - soft_tp,
            },
        },
        "per_slot": {
            s: {
                "gold_filled": slot_gold[s],
                "tp": slot_tp[s],
                "fn_omit": slot_fn_omit[s],
                "fn_wrong": slot_fn_wrong[s],
                "fp_pred_only": slot_fp[s],
            }
            for s in CPC_SLOT_NAMES
            if slot_gold[s] or slot_tp[s] or slot_fn_omit[s] or slot_fn_wrong[s] or slot_fp[s]
        },
        "tp_examples": tp_examples,
        "wrong_value_examples": wrong_examples,
        "near_miss_token_overlap": near,
        "omit_examples": omit_examples,
        "sample_raw_cpc": sample_raw_cpc,
        "slot_names": list(CPC_SLOT_NAMES),
    }


def wording_summary(rows: list[dict]) -> dict:
    systems = list(PRED)
    summary = {}
    for name in systems:
        asked = q = all_c = any_c = target = refuse = execute = 0
        cover_hist = Counter()
        for row in rows:
            s = row["systems"].get(name)
            if not s:
                continue
            if s["route"] == "clarify":
                asked += 1
            elif s["route"] in ("face_preserving_rejection", "reject"):
                refuse += 1
            elif s["route"] in ("execute", "silently_resolve"):
                execute += 1
            if s["question"]:
                q += 1
            if s["all_covered"]:
                all_c += 1
            if s["any_covered"]:
                any_c += 1
            cover_hist[s["n_covered"]] += 1
            if s["target_subset"]:
                target += 1
        summary[name] = {
            "asked": asked,
            "questions": q,
            "all_must_convey": all_c,
            "any_must_convey_item": any_c,
            "target_set_exact_subset": target,
            "refused_gold_ask": refuse,
            "executed_gold_ask": execute,
            "n_must_items_covered_histogram": dict(cover_hist),
        }
    return summary


def main() -> None:
    rows = wording_rows()
    report = {
        "n_gold_ask": len(rows),
        "wording_summary": wording_summary(rows),
        "wording_rows": rows,
        "cpc_goal_first": cpc_diag(),
    }
    out = ROOT / "outputs" / "wording_cpc_deepdive_20260914.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "n": len(rows), "wording_summary": report["wording_summary"], "cpc_micro": report["cpc_goal_first"]["micro"], "cpc_fill_rows": report["cpc_goal_first"]["n_rows_with_any_fill"]}, indent=2))


if __name__ == "__main__":
    main()
