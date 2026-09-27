#!/usr/bin/env python3
"""Early 8B vs 1.7B compare on Pilot-120 @ T0.7 (goal-first)."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ambiguity_manager.evaluation import pilot_120 as p120  # noqa: E402

_CONTENT_RE = re.compile(r"[a-z0-9]+", re.I)
_NEG = {"not", "no", "never", "dont", "don't", "cannot", "cant", "can't", "refuse", "forbidden"}


def content_tokens(text: str) -> set[str]:
    return {t.lower() for t in _CONTENT_RE.findall(text or "") if len(t) > 1}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or b and not a:
        return 0.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def polarity_flip(pred: str, ref: str) -> bool:
    pt, rt = content_tokens(pred), content_tokens(ref)
    return bool(pt & _NEG) != bool(rt & _NEG) and bool(pt & rt)


def intent_pass(pred_summary: str, gold: dict[str, Any], thr: float = 0.18) -> bool:
    refs = [
        str(gold.get("reference_A_intent_text") or ""),
        str(gold.get("reference_B_intent_text") or ""),
        str(gold.get("intent_reference_A") or ""),
        str(gold.get("intent_reference_B") or ""),
    ]
    # also nested
    for key in ("intent", "interpretation"):
        blob = gold.get(key)
        if isinstance(blob, dict):
            refs.extend(
                [
                    str(blob.get("reference_A_intent_text") or ""),
                    str(blob.get("reference_B_intent_text") or ""),
                ]
            )
    pt = content_tokens(pred_summary)
    best = 0.0
    for ref in refs:
        if not ref.strip():
            continue
        if polarity_flip(pred_summary, ref):
            continue
        best = max(best, jaccard(pt, content_tokens(ref)))
    return best >= thr


def norm_route(x: Any) -> str:
    s = str(x or "").strip().lower()
    if s in {"execute", "act", "go"}:
        return "execute"
    if s in {"clarify", "ask", "clarify_then_act"}:
        return "clarify"
    if s in {"refuse", "reject", "face_preserving_rejection", "face-preserving-rejection"}:
        return "refuse"
    return s


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_preds(path: Path) -> dict[str, dict[str, Any]]:
    return {str(r["record_id"]): r for r in load_jsonl(path)}


def score_system(preds: dict[str, dict[str, Any]], gold_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    n = len(gold_by_id)
    intent_ok = route_ok = failed = missing = 0
    routes = Counter()
    caps = Counter()
    lats: list[float] = []
    for rid, g in gold_by_id.items():
        p = preds.get(rid)
        if p is None:
            missing += 1
            continue
        if p.get("failed"):
            failed += 1
            continue
        intent = str(p.get("intent_summary") or "")
        if intent_pass(intent, g):
            intent_ok += 1
        pred_route = norm_route(p.get("terminal_strategy") or p.get("route"))
        gold_route = norm_route(g.get("gold_route") or g.get("route") or g.get("handling_path"))
        routes[pred_route] += 1
        caps[str(p.get("capability_status"))] += 1
        if pred_route == gold_route and gold_route:
            route_ok += 1
        if p.get("latency_ms") is not None:
            lats.append(float(p["latency_ms"]))
    return {
        "n_gold": n,
        "n_preds": len(preds),
        "missing": missing,
        "failed": failed,
        "scored_ok_rows": n - missing - failed,
        "intent_auto": intent_ok,
        "intent_auto_den": n,  # failed/missing count as miss
        "routing": route_ok,
        "routing_den": n,
        "pred_route_dist": dict(routes),
        "capability_dist": dict(caps),
        "latency_s_mean": (sum(lats) / len(lats) / 1000.0) if lats else None,
        "latency_s_median": (sorted(lats)[len(lats) // 2] / 1000.0) if lats else None,
    }


def discover_gold(root: Path) -> dict[str, dict[str, Any]]:
    # Prefer interpretation gold + route gold merge used in Pilot-120.
    out: dict[str, dict[str, Any]] = {}
    intent_path = root / "pilot120_t41_complete_closure/final_t41/pilot120_interpretation_gold_final.jsonl"
    alt_intent = list(root.glob("**/pilot120_interpretation_gold_final.jsonl"))
    if not intent_path.exists() and alt_intent:
        intent_path = alt_intent[0]
    route_candidates = [
        root / "data/annotations/pilot_120_v1/pilot_120_gold_official.jsonl",
        root / "data/annotations/pilot_120_v1/gold_official.jsonl",
        root / "data/annotations/pilot_120_v1/pilot_120_v1_gold.jsonl",
    ]
    # Also search
    route_candidates.extend(root.glob("data/annotations/pilot_120_v1/*gold*.jsonl"))

    if intent_path.exists():
        for r in load_jsonl(intent_path):
            rid = str(r.get("record_id"))
            out[rid] = dict(r)

    for rp in route_candidates:
        if not rp.exists():
            continue
        for r in load_jsonl(rp):
            rid = str(r.get("record_id"))
            if rid not in out:
                out[rid] = {}
            out[rid].update({k: v for k, v in r.items() if v is not None})
            # normalize route field
            for k in ("gold_route", "route", "handling_path", "canonical_route"):
                if r.get(k):
                    out[rid]["gold_route"] = r[k]
                    break
        if out:
            break

    # Fallback: p120 package
    if len(out) < 100:
        try:
            paths = p120.default_paths(root)
            # try known loaders
            for name in dir(p120):
                if "gold" in name.lower() and callable(getattr(p120, name)):
                    pass
        except Exception:
            pass
    return out


def main() -> int:
    code = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
    pred_1p7 = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
        "/home-mscluster/mbangie/t12-hpc/results/pilot120_latency_1p7b-20260918/T0.7/predictions/goal_first_manager_v2.predictions.jsonl"
    )
    pred_8b = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(
        "/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915/T0.7/predictions/goal_first_manager_v2.predictions.jsonl"
    )

    gold = discover_gold(code)
    print("gold_n", len(gold))
    if gold:
        sample = next(iter(gold.values()))
        print("gold_sample_keys", sorted(sample.keys())[:40])

    p1 = load_preds(pred_1p7) if pred_1p7.exists() else {}
    p8 = load_preds(pred_8b) if pred_8b.exists() else {}
    print("n_1p7", len(p1), "n_8b", len(p8), "failed_1p7", sum(1 for r in p1.values() if r.get("failed")))

    s1 = score_system(p1, gold) if gold and p1 else {}
    s8 = score_system(p8, gold) if gold and p8 else {}
    out = {
        "note": "Early compare; 1.7B may be mid-repair (failed rows stripped). Intent = Jaccard>=0.18 auto screen.",
        "pred_1p7": str(pred_1p7),
        "pred_8b": str(pred_8b),
        "qwen3_1p7b": s1,
        "qwen3_8b": s8,
    }
    print(json.dumps(out, indent=2))
    out_path = Path(sys.argv[4]) if len(sys.argv) > 4 else pred_1p7.parent.parent / "scores" / "early_8b_vs_1p7b.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
