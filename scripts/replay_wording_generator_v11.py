#!/usr/bin/env python3
"""CPU replay: new clarification generator on frozen goal-first analyses.

Does not mutate official wording 0/23. Writes unofficial lift numbers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from score_official_sidecar_followon import (  # noqa: E402
    OFFICIAL_WORDING,
    _first,
    _item_covered,
    _tokens,
)
from score_pilot120_cpc_and_risk import load_jsonl  # noqa: E402
from ambiguity_manager.systems.contracts import StructuredAnalysis  # noqa: E402
from ambiguity_manager.systems.response_generation import generate_clarification  # noqa: E402

PRED = ROOT / "outputs/cluster_pulls/r1_manager/predictions/goal_first_manager_v2.predictions.jsonl"


def cover(items, blob: str) -> bool:
    token_sets = [_tokens(x) for x in items]
    shared = set.intersection(*token_sets) if token_sets else set()
    bt = _tokens(blob)
    return all(_item_covered(item, bt, shared) for item in items)


def main() -> None:
    gold = load_jsonl(OFFICIAL_WORDING)
    pred = load_jsonl(PRED)
    rows = []
    old_ok = new_ok = asked = 0
    for rid, grow in sorted(gold.items()):
        items = grow["gold_clarification"]["wording_criteria"]["must_convey"]
        row = pred[rid]
        parsed = row.get("parsed") if isinstance(row.get("parsed"), dict) else {}
        analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
        route = row.get("terminal_strategy")
        old_q = _first(parsed.get("clarification_question"), analysis.get("clarification_question"))
        summary = str(_first(row.get("intent_summary"), analysis.get("intent_summary")) or "")
        targets = list(
            _first(parsed.get("clarification_targets"), analysis.get("clarification_targets"), []) or []
        )
        new_q = None
        if route == "clarify":
            asked += 1
            new_q = generate_clarification(StructuredAnalysis(intent_summary=summary), targets)
        old_pass = bool(old_q) and cover(items, str(old_q))
        new_pass = bool(new_q) and cover(items, str(new_q))
        if old_pass:
            old_ok += 1
        if new_pass:
            new_ok += 1
        rows.append(
            {
                "record_id": rid,
                "route": route,
                "old_q": old_q,
                "new_q": new_q,
                "old_pass": old_pass,
                "new_pass": new_pass,
                "must_convey": items,
            }
        )
    out = {
        "note": "Unofficial CPU replay of clarification generator 1.1.0 on frozen intent_summary. Official wording stays 0/23.",
        "denominator": 23,
        "asked": asked,
        "official_wording_correct": old_ok,
        "replay_wording_correct": new_ok,
        "rows": rows,
    }
    path = ROOT / "outputs" / "wording_generator_replay_20260914.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in out if k != "rows"}, indent=2))
    for r in rows:
        if r["new_q"] and r["new_q"] != r["old_q"]:
            print(r["record_id"], "NEW", r["new_q"], "PASS" if r["new_pass"] else "fail")


if __name__ == "__main__":
    main()
