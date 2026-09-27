#!/usr/bin/env python3
"""If CPC answers sit in value but status is not 'filled', F1 is fake-low."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from score_official_sidecar_followon import OFFICIAL_CPC, _tokens  # noqa: E402
from score_pilot120_cpc_and_risk import load_jsonl  # noqa: E402
from ambiguity_manager.evaluation.evaluator import DeterministicEvaluator  # noqa: E402
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES  # noqa: E402

PRED = ROOT / "outputs/cluster_pulls/r1_manager/predictions/goal_first_manager_v2.predictions.jsonl"
EMPTY = {"", "none", "null", "unknown", "unassigned", "n/a", "na", "not applicable"}


def pred_cpc(row):
    parsed = row.get("parsed") if isinstance(row.get("parsed"), dict) else {}
    analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
    return analysis.get("cpc") or parsed.get("cpc") or {}


def cell_value(cell):
    if isinstance(cell, dict):
        return cell.get("value"), cell.get("status")
    if cell in (None, "", {}, []):
        return None, None
    return cell, "scalar"


def usable(val) -> bool:
    if val is None:
        return False
    if isinstance(val, list):
        return any(usable(x) for x in val)
    s = str(val).strip().casefold()
    return s not in EMPTY


def main() -> None:
    gold = load_jsonl(OFFICIAL_CPC)
    pred = load_jsonl(PRED)
    ev = DeterministicEvaluator()
    rules = ev.norm.get("rules", {})

    status_when_usable = Counter()
    usable_cells = 0
    official_filled = 0
    tp_off = fp_off = fn_off = 0
    tp_val = fp_val = fn_omit_val = fn_wrong_val = 0
    near = 0
    examples_hidden = []

    def norm(v):
        g, _ = ev._extract_filled_cpc({"_": {"status": "filled", "value": v}}, {}, rules)
        # hack - just use evaluator normalise via a fake slot
        return ev._extract_filled_cpc({"action": {"status": "filled", "value": v}}, {}, rules)[0].get("action")

    for rid, grow in gold.items():
        gcpc = grow["gold_cpc"]
        pcpc = pred_cpc(pred[rid])
        gfill, pfill_official = ev._extract_filled_cpc(gcpc, pcpc, rules)
        pfill_value = {}
        for slot in CPC_SLOT_NAMES:
            val, status = cell_value(pcpc.get(slot))
            if status == "filled" and val is not None:
                official_filled += 1
            if usable(val):
                usable_cells += 1
                status_when_usable[str(status)] += 1
                pfill_value[slot] = ev._extract_filled_cpc(
                    {slot: {"status": "filled", "value": val}}, {}, rules
                )[0].get(slot)
                if status != "filled" and len(examples_hidden) < 20:
                    examples_hidden.append(
                        {
                            "record_id": rid,
                            "slot": slot,
                            "status": status,
                            "pred_value": val,
                            "gold": (gcpc.get(slot) or {}).get("value") if isinstance(gcpc.get(slot), dict) else gcpc.get(slot),
                            "gold_status": (gcpc.get(slot) or {}).get("status") if isinstance(gcpc.get(slot), dict) else None,
                        }
                    )

        # official
        for slot in set(gfill) | set(pfill_official):
            gv, pv = gfill.get(slot), pfill_official.get(slot)
            if gv is not None and pv == gv:
                tp_off += 1
            elif gv is not None and pv is None:
                fn_off += 1
            elif gv is not None:
                fn_off += 1
                fp_off += 1
            elif pv is not None:
                fp_off += 1

        # value-regardless-of-status
        for slot in set(gfill) | set(pfill_value):
            gv, pv = gfill.get(slot), pfill_value.get(slot)
            if gv is not None and pv == gv:
                tp_val += 1
            elif gv is not None and pv is None:
                fn_omit_val += 1
            elif gv is not None and pv is not None:
                fn_wrong_val += 1
                fp_val += 1
                gt, pt = _tokens(str(gv)), _tokens(str(pv))
                if gt and pt and len(gt & pt) / len(gt | pt) >= 0.5:
                    near += 1
            elif pv is not None:
                fp_val += 1

    def f1(tp, fp, fn):
        p = tp / (tp + fp) if tp + fp else None
        r = tp / (tp + fn) if tp + fn else None
        f = None if p is None or r is None or p + r == 0 else 2 * p * r / (p + r)
        return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f}

    out = {
        "official_status_filled_cells": official_filled,
        "cells_with_usable_value": usable_cells,
        "status_when_value_usable": dict(status_when_usable),
        "official_micro": f1(tp_off, fp_off, fn_off),
        "if_any_usable_value_counted_as_fill": f1(tp_val, fp_val, fn_omit_val + fn_wrong_val),
        "split_value_scored": {
            "tp": tp_val,
            "fp": fp_val,
            "fn_omit": fn_omit_val,
            "fn_wrong": fn_wrong_val,
            "wrong_but_jaccard_ge_0.5": near,
        },
        "hidden_value_examples": examples_hidden,
    }
    Path("outputs/cpc_status_vs_value_20260914.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in out if k != "hidden_value_examples"}, indent=2))
    print("hidden examples:")
    for e in examples_hidden[:12]:
        print(e)


if __name__ == "__main__":
    main()
