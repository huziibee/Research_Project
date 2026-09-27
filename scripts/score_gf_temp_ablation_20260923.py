#!/usr/bin/env python3
"""Score Goal-First temperature ablation: exact route + automatic intent screen.

Intent is the Jaccard>=0.18 automatic screen with polarity-flip skip
(same family as the paper H3/H4 table). Not official two-judge.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

_CONTENT_RE = re.compile(r"[a-z0-9]+", re.I)
_NEG = {"not", "no", "never", "dont", "don't", "cannot", "cant", "can't", "refuse", "forbidden"}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def norm_route(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"face_preserving_rejection", "reject", "refuse", "rejection"}:
        return "refuse"
    if text in {"clarify", "clarification", "ask"}:
        return "clarify"
    if text in {"execute", "act", "silently_resolve"}:
        return "execute"
    return text or "missing"


def content_tokens(text: str) -> set[str]:
    return {t.lower() for t in _CONTENT_RE.findall(text or "") if len(t) > 1}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def polarity_flip(pred: str, ref: str) -> bool:
    pt, rt = content_tokens(pred), content_tokens(ref)
    pn, rn = bool(pt & _NEG), bool(rt & _NEG)
    return pn != rn and bool(pt & rt)


def intent_pass(pred_summary: str, gold: dict[str, Any], thr: float = 0.18) -> bool:
    refs = [
        str(gold.get("reference_A_intent_text") or ""),
        str(gold.get("reference_B_intent_text") or ""),
    ]
    best = 0.0
    for ref in refs:
        if not ref.strip():
            continue
        if polarity_flip(pred_summary, ref):
            continue
        best = max(best, jaccard(content_tokens(pred_summary), content_tokens(ref)))
    return best >= thr


def load_gold_and_refs(root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    gold_path = root / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl"
    gold = {row["record_id"]: row for row in load_jsonl(gold_path)}
    ids = [row["record_id"] for row in load_jsonl(gold_path)]
    candidates = [
        root
        / "pilot120_intent_evaluation_20260902"
        / "pilot120_intent_evaluation_20260902"
        / "validation"
        / "self_contained_rebuild"
        / "data"
        / "intent_gold_references_120.jsonl",
        root
        / "pilot120_intent_evaluation_20260902"
        / "pilot120_intent_evaluation_20260902"
        / "data"
        / "intent_gold_references_120.jsonl",
        root / "data/annotations/pilot_120_v1/intent_gold_references_120.jsonl",
    ]
    refs_path = next((p for p in candidates if p.exists() and p.stat().st_size > 1000), None)
    if refs_path is None:
        refs_path = candidates[0]
    refs = {row["record_id"]: row for row in load_jsonl(refs_path)} if refs_path.exists() else {}
    for rid, row in gold.items():
        if rid in refs:
            row = dict(row)
            row["reference_A_intent_text"] = refs[rid].get("reference_A_intent_text")
            row["reference_B_intent_text"] = refs[rid].get("reference_B_intent_text")
            gold[rid] = row
    return gold, ids


def score_predictions(pred_path: Path, gold: dict[str, dict[str, Any]], ids: list[str]) -> dict[str, Any]:
    prediction_rows = load_jsonl(pred_path)
    prediction_ids = [row["record_id"] for row in prediction_rows]
    if len(prediction_rows) != 120 or len(set(prediction_ids)) != 120 or prediction_ids != ids:
        raise ValueError(f"prediction_count_or_id_order_mismatch:{pred_path}")
    rows = {row["record_id"]: row for row in prediction_rows}
    route_ok = 0
    intent_ok = 0
    failed = 0
    confusion: dict[str, int] = {}
    for rid in ids:
        pred = rows.get(rid) or {}
        g = gold[rid]
        if pred.get("failed"):
            failed += 1
            key = f"{norm_route(g.get('terminal_strategy'))}->failed"
            confusion[key] = confusion.get(key, 0) + 1
            continue
        g_route = norm_route(g.get("terminal_strategy"))
        p_route = norm_route(pred.get("terminal_strategy"))
        if p_route == g_route:
            route_ok += 1
        key = f"{g_route}->{p_route}"
        confusion[key] = confusion.get(key, 0) + 1
        if intent_pass(str(pred.get("intent_summary") or ""), g):
            intent_ok += 1
    return {
        "n": 120,
        "unique_pred_ids": len(rows),
        "order_ok": True,
        "exact_route": route_ok,
        "intent_screen": intent_ok,
        "failed_in_denominator": failed,
        "confusion_gold_pred": confusion,
        "pred_path": str(pred_path),
        "metric_note": "intent_screen is automatic Jaccard>=0.18 with polarity-flip skip; not official two-judge",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--pred", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--label", type=str, default="")
    args = parser.parse_args()
    gold, ids = load_gold_and_refs(args.root.resolve())
    payload = score_predictions(args.pred.resolve(), gold, ids)
    payload["temperature"] = args.temperature
    payload["seed"] = args.seed
    payload["label"] = args.label
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
