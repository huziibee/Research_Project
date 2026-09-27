#!/usr/bin/env python3
"""Follow-on: is the content in intent_summary / candidates, and why CPC is empty?"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from score_official_sidecar_followon import (  # noqa: E402
    OFFICIAL_CPC,
    OFFICIAL_WORDING,
    _first,
    _item_covered,
    _tokens,
)
from score_pilot120_cpc_and_risk import load_jsonl  # noqa: E402
from ambiguity_manager.evaluation.evaluator import DeterministicEvaluator  # noqa: E402
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES  # noqa: E402

PRED_GF = ROOT / "outputs/cluster_pulls/r1_manager/predictions/goal_first_manager_v2.predictions.jsonl"
PRED_RAW = ROOT / "outputs/t45_historical_reconciliation_local_20260901/inputs/direct_base_llm.predictions.jsonl"


def qtype(question: str | None) -> str:
    if not question:
        return "none"
    q = question.casefold()
    slotish = [
        "spatial relation",
        "which action",
        "the contextual",
        "the quantitative",
        "object attributes",
        "before i continue, could you clarify:",
        "could you clarify the",
    ]
    if any(s in q for s in slotish):
        return "slot_name_template"
    if "?" in q:
        return "natural_question"
    return "other_text"


def cover_blob(items: list[str], blob: str) -> dict:
    token_sets = [_tokens(x) for x in items]
    shared = set.intersection(*token_sets) if token_sets else set()
    bt = _tokens(blob)
    per = [_item_covered(item, bt, shared) for item in items]
    return {"n_covered": sum(per), "n": len(items), "all": all(per) and bool(blob.strip())}


def main() -> None:
    gold_w = load_jsonl(OFFICIAL_WORDING)
    gf = load_jsonl(PRED_GF)
    raw = load_jsonl(PRED_RAW)
    gold_cpc = load_jsonl(OFFICIAL_CPC)
    ev = DeterministicEvaluator()
    rules = ev.norm.get("rules", {})

    wording = []
    qtypes = Counter()
    summary_all = summary_any = 0
    cand_all = cand_any = 0
    for rid, grow in sorted(gold_w.items()):
        items = grow["gold_clarification"]["wording_criteria"]["must_convey"]
        row = gf[rid]
        parsed = row.get("parsed") if isinstance(row.get("parsed"), dict) else {}
        analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
        q = _first(parsed.get("clarification_question"), analysis.get("clarification_question"))
        summary = str(_first(row.get("intent_summary"), analysis.get("intent_summary")) or "")
        cands = analysis.get("candidate_interpretations") or parsed.get("candidate_interpretations") or []
        cand_blob = json.dumps(cands, ensure_ascii=False)
        qt = qtype(q)
        qtypes[qt] += 1
        s_cov = cover_blob(items, summary)
        c_cov = cover_blob(items, cand_blob)
        q_cov = cover_blob(items, str(q or ""))
        if s_cov["all"]:
            summary_all += 1
        if s_cov["n_covered"]:
            summary_any += 1
        if c_cov["all"]:
            cand_all += 1
        if c_cov["n_covered"]:
            cand_any += 1
        wording.append(
            {
                "record_id": rid,
                "route": row.get("terminal_strategy"),
                "question_type": qt,
                "question": q,
                "must_convey": items,
                "question_cover": q_cov,
                "intent_summary_cover": s_cov,
                "intent_summary": summary[:400],
                "candidate_cover": c_cov,
                "n_candidates": len(cands) if isinstance(cands, list) else 0,
            }
        )

    # raw qwen: any question-like span in raw_output?
    raw_q_stats = {"asked": 0, "raw_has_qmark": 0, "parsed_q": 0}
    for rid in gold_w:
        row = raw[rid]
        parsed = row.get("parsed") if isinstance(row.get("parsed"), dict) else {}
        if row.get("terminal_strategy") == "clarify":
            raw_q_stats["asked"] += 1
        if parsed.get("clarification_question") or row.get("clarification_question"):
            raw_q_stats["parsed_q"] += 1
        if "?" in str(row.get("raw_output") or ""):
            raw_q_stats["raw_has_qmark"] += 1

    # CPC fill vs route
    fill_by_route = Counter()
    unknown_only = 0
    cand_filled_cells = 0
    analysis_filled_cells = 0
    rows_cand_has_fill_analysis_empty = 0
    for rid, row in gf.items():
        parsed = row.get("parsed") if isinstance(row.get("parsed"), dict) else {}
        analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
        cpc = analysis.get("cpc") or {}
        gfill, pfill = ev._extract_filled_cpc(gold_cpc[rid]["gold_cpc"], cpc, rules)
        analysis_filled_cells += len(pfill)
        if pfill:
            fill_by_route[str(row.get("terminal_strategy"))] += 1
        else:
            unknown_only += 1
        cands = analysis.get("candidate_interpretations") or []
        row_cand_fill = 0
        if isinstance(cands, list):
            for cand in cands:
                if not isinstance(cand, dict):
                    continue
                cf = ev._extract_filled_cpc(cand.get("cpc") or {}, {}, rules)[0]
                row_cand_fill += len(cf)
        cand_filled_cells += row_cand_fill
        if row_cand_fill and not pfill:
            rows_cand_has_fill_analysis_empty += 1

    # Gold action top values vs pred unknown rate for action
    action_gold_status_when_pred_unknown = Counter()
    for rid, grow in gold_cpc.items():
        g = (grow.get("gold_cpc") or {}).get("action") or {}
        parsed = gf[rid].get("parsed") if isinstance(gf[rid].get("parsed"), dict) else {}
        analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
        p = (analysis.get("cpc") or {}).get("action") or {}
        if isinstance(p, dict) and p.get("status") != "filled":
            action_gold_status_when_pred_unknown[str(g.get("status"))] += 1

    out = {
        "wording_question_types": dict(qtypes),
        "unofficial_if_we_scored_intent_summary": {
            "all_must_convey": summary_all,
            "any_item": summary_any,
            "n": 23,
        },
        "unofficial_if_we_scored_candidate_interpretations": {
            "all_must_convey": cand_all,
            "any_item": cand_any,
            "n": 23,
        },
        "raw_qwen_gold_ask": raw_q_stats,
        "cpc": {
            "analysis_filled_cells": analysis_filled_cells,
            "candidate_filled_cells_sum": cand_filled_cells,
            "rows_with_candidate_fill_but_empty_analysis_cpc": rows_cand_has_fill_analysis_empty,
            "rows_analysis_cpc_empty": unknown_only,
            "filled_rows_by_route": dict(fill_by_route),
            "action_gold_status_when_pred_action_not_filled": dict(action_gold_status_when_pred_unknown),
        },
        "wording_rows": wording,
    }
    path = ROOT / "outputs" / "wording_cpc_content_audit_20260914.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in out if k != "wording_rows"}, indent=2))
    print("--- intent_summary that covers ALL must_convey ---")
    for row in wording:
        if row["intent_summary_cover"]["all"]:
            print(row["record_id"], row["route"], row["must_convey"])
            print(" ", row["intent_summary"][:240])
            print(" Q", row["question"])


if __name__ == "__main__":
    main()
