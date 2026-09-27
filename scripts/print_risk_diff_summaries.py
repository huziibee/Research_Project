#!/usr/bin/env python3
import json
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "data/annotations/pilot_120_v1/gold_v2_officialization_20260914/risk/COMPARE.json"
d = json.loads(p.read_text(encoding="utf-8"))
for pair in [
    "none->low",
    "none->medium",
    "low->medium",
    "high->medium",
    "medium->high",
    "medium->unknown",
    "unknown->high",
]:
    rows = [x for x in d["diffs"] if x["pair"] == pair]
    print("=" * 80)
    print(pair, len(rows))
    for r in rows:
        cmd = (r["command"] or "").replace("\n", " ")
        print(f"{r['record_id']}|{r['gpt_a']}/{r['grok_b']}|{cmd[:160]}")
        print(f"  A: {(r['gpt_rationale'] or '')[:220]}")
        print(f"  B: {(r['grok_rationale'] or '')[:220]}")
