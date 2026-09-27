#!/usr/bin/env bash
set -euo pipefail
echo "=== QUEUE ==="
squeue -u mbangie || true
echo
python3 <<'PY'
import json
from pathlib import Path
from collections import Counter

root = Path("/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911/manager")
pred = root / "predictions"
systems = [
    "goal_first_manager_v2",
    "rich_conservative_manager_v2",
    "degree_based_router_v2",
    "goal_first_context_blind_v2",
]
out = {"systems": {}, "unique_full": [], "unique_blind": []}
full, blind = set(), set()
for sid in systems:
    path = pred / f"{sid}.predictions.jsonl"
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    fails = [r for r in rows if r.get("failed") is True]
    reasons = Counter()
    items = []
    for r in fails:
        reason = (
            r.get("failure_reason")
            or r.get("error")
            or r.get("fail_reason")
            or r.get("analysis_error")
            or r.get("parse_error")
            or "unknown"
        )
        reasons[str(reason)[:100]] += 1
        raw_keys = [k for k in r.keys() if "raw" in k.lower() or "generat" in k.lower() or "text" in k.lower()]
        items.append(
            {
                "record_id": r.get("record_id"),
                "reason": str(reason)[:120],
                "has_raw_keys": raw_keys,
                "intent_summary": (r.get("intent_summary") or "")[:160],
                "terminal_strategy": r.get("terminal_strategy"),
            }
        )
        print(f"{sid}\t{r.get('record_id')}\t{reason}\traw_keys={raw_keys}")
    out["systems"][sid] = {
        "n_failed": len(fails),
        "reason_counts": dict(reasons),
        "ids": [r.get("record_id") for r in fails],
        "items": items,
    }
    print(f"SUMMARY {sid} n={len(fails)} reasons={dict(reasons)}")
    ids = {r["record_id"] for r in fails}
    if "blind" in sid:
        blind |= ids
    else:
        full |= ids
    if fails:
        sample = fails[0]
        print("SAMPLE_KEYS", sorted(sample.keys()))
        for k, v in sample.items():
            if isinstance(v, str) and len(v) > 120:
                print(f"  STR {k} len={len(v)} head={v[:200]!r}")

out["unique_full"] = sorted(full)
out["unique_blind"] = sorted(blind)
print("UNIQUE_FULL", out["unique_full"])
print("UNIQUE_BLIND", out["unique_blind"])
print("n_full", len(full), "n_blind", len(blind))
inv = root / "failed_inventory_20260912.json"
inv.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
print("wrote", inv)
PY
