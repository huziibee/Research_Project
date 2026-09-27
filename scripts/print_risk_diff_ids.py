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
    print(pair, [r["record_id"] for r in rows])
print("UNKNOWNS", [r["record_id"] for r in d["unknowns"]])
print("HIGH_FLIPS", [r["record_id"] for r in d["high_flips"]])
