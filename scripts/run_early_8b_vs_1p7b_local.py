#!/usr/bin/env python3
"""Early 8B vs 1.7B scoreboard @ T0.7 (local)."""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from sprint_capability_ambiguity_rescue_20260918 import intent_pass  # noqa: E402


def load_jsonl(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[str(row["record_id"])] = row
    return out


def norm_route(x) -> str:
    s = str(x or "").strip().lower()
    if s in {"execute", "act", "go"}:
        return "execute"
    if s in {"clarify", "ask", "clarify_then_act"}:
        return "clarify"
    if s in {"refuse", "reject", "face_preserving_rejection", "face-preserving-rejection"}:
        return "refuse"
    return s


def score(preds: dict, gold: dict, refs: dict, label: str) -> dict:
    intent_ok = route_ok = failed = missing = 0
    routes: Counter[str] = Counter()
    caps: Counter[str] = Counter()
    lats: list[float] = []
    for rid, g in gold.items():
        p = preds.get(rid)
        if p is None:
            missing += 1
            continue
        if p.get("failed"):
            failed += 1
            continue
        g2 = dict(g)
        if rid in refs:
            g2["reference_A_intent_text"] = refs[rid].get("reference_A_intent_text")
            g2["reference_B_intent_text"] = refs[rid].get("reference_B_intent_text")
        summary = str(p.get("intent_summary") or "")
        if intent_pass(summary, g2):
            intent_ok += 1
        pr = norm_route(p.get("terminal_strategy"))
        gr = norm_route(g.get("terminal_strategy"))
        routes[pr] += 1
        caps[str(p.get("capability_status"))] += 1
        if pr == gr:
            route_ok += 1
        if p.get("latency_ms") is not None:
            lats.append(float(p["latency_ms"]))
    return {
        "label": label,
        "n_preds": len(preds),
        "missing": missing,
        "failed": failed,
        "intent_auto": f"{intent_ok}/120",
        "intent_auto_n": intent_ok,
        "routing": f"{route_ok}/120",
        "routing_n": route_ok,
        "route_dist": dict(routes),
        "cap_dist": dict(caps),
        "latency_s_mean": round(sum(lats) / len(lats) / 1000, 2) if lats else None,
        "latency_s_median": round(sorted(lats)[len(lats) // 2] / 1000, 2) if lats else None,
        "execute_count": routes.get("execute", 0),
        "clarify_count": routes.get("clarify", 0),
        "refuse_count": routes.get("refuse", 0),
    }


def main() -> int:
    tmp = Path(os.environ["TEMP"]) / "p120_early_cmp"
    p1 = load_jsonl(tmp / "1p7b_gfv2.jsonl")
    p8 = load_jsonl(tmp / "8b_gfv2.jsonl")
    gold = load_jsonl(ROOT / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl")
    refs_path = (
        ROOT
        / "pilot120_intent_evaluation_20260902"
        / "pilot120_intent_evaluation_20260902"
        / "validation"
        / "self_contained_rebuild"
        / "data"
        / "intent_gold_references_120.jsonl"
    )
    if not refs_path.exists():
        refs_path = ROOT / "data/annotations/pilot_120_v1/intent_gold_references_120.jsonl"
    refs = load_jsonl(refs_path) if refs_path.exists() else {}

    # Completed-job latency summary (includes failed rows in mean)
    lat_summary = {}
    ls = tmp / "latency_summary.json"
    if ls.exists():
        lat_summary = json.loads(ls.read_text(encoding="utf-8"))

    out = {
        "early_compare": True,
        "note": (
            "1.7B snapshot may be mid-repair (failed rows stripped). "
            "Missing/failed count against /120. "
            "8B is unified T0.7 goal-first. Intent = automatic overlap Jaccard>=0.18."
        ),
        "completed_job_latency_summary": lat_summary,
        "qwen3_1p7b": score(p1, gold, refs, "Qwen3-1.7B (current snapshot)"),
        "qwen3_8b": score(p8, gold, refs, "Qwen3-8B T0.7 unified"),
    }
    out_path = ROOT / "outputs/sprint_rescue_20260918/early_8b_vs_1p7b_T0.7.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
