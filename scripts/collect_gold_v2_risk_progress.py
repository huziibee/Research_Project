#!/usr/bin/env python3
"""Count Grok B risk writes and diff against GPT A when both exist."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "annotations" / "pilot_120_v1" / "gold_v2_officialization_20260914" / "risk"
IDS = json.loads((BASE / "RECORD_IDS.json").read_text(encoding="utf-8"))


def load_one(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> None:
    done = []
    missing = []
    agrees = []
    diffs = []
    grok_counts: Counter[str] = Counter()
    for rid in IDS:
        b = load_one(BASE / "annotator_b_grok" / f"{rid}.json")
        a = load_one(BASE / "annotator_a_gpt" / f"{rid}.json")
        if not b or b.get("gold_risk_level") not in {"none", "low", "medium", "high", "unknown"}:
            missing.append(rid)
            continue
        done.append(rid)
        grok_counts[b["gold_risk_level"]] += 1
        if a and a.get("gold_risk_level") == b["gold_risk_level"]:
            agrees.append(rid)
        elif a:
            diffs.append(
                {
                    "record_id": rid,
                    "gpt_a": a.get("gold_risk_level"),
                    "grok_b": b.get("gold_risk_level"),
                }
            )
    print(
        json.dumps(
            {
                "done": len(done),
                "missing": len(missing),
                "next_missing": missing[:12],
                "agree_so_far": len(agrees),
                "diff_so_far": len(diffs),
                "grok_counts": dict(grok_counts),
                "diffs_preview": diffs[:15],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
