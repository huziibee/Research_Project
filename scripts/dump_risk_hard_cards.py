#!/usr/bin/env python3
import json
from pathlib import Path

base = Path(__file__).resolve().parents[1] / "data/annotations/pilot_120_v1/gold_v2_officialization_20260914/risk"
cmp = json.loads((base / "COMPARE.json").read_text(encoding="utf-8"))
hard = [x for x in cmp["diffs"] if x["pair"] != "none->low"]
out = []
for r in hard:
    out.append(
        {
            "record_id": r["record_id"],
            "pair": r["pair"],
            "command": r["command"],
            "dialogue_history": r["dialogue_history"],
            "scene_context": r["scene_context"],
            "capability_context": r["capability_context"],
            "gpt_a": r["gpt_a"],
            "grok_b": r["grok_b"],
            "gpt_rationale": r["gpt_rationale"],
            "grok_rationale": r["grok_rationale"],
        }
    )
dest = base / "HARD_DIFFS.json"
dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {len(out)} hard diffs")
