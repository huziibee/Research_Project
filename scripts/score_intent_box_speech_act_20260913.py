#!/usr/bin/env python3
"""Speech-act exact on new intent-box predictions vs Pilot-120 gold. CPU only."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    pred_path = Path(sys.argv[1])
    gold_path = Path(sys.argv[2])
    out_path = Path(sys.argv[3])
    gold = {row["record_id"]: row.get("speech_act") for row in load_jsonl(gold_path)}
    pred = load_jsonl(pred_path)
    n = 0
    exact = 0
    indirect_n = 0
    indirect_hit = 0
    for row in pred:
        rid = row["record_id"]
        g = gold.get(rid)
        p = row.get("speech_act") or (row.get("parsed") or {}).get("speech_act")
        if g is None:
            continue
        n += 1
        if p == g:
            exact += 1
        if g == "indirect_request":
            indirect_n += 1
            if p == g:
                indirect_hit += 1
    payload = {
        "predictions": str(pred_path),
        "n": n,
        "exact": exact,
        "exact_rate": (exact / n) if n else None,
        "indirect_request": {"n": indirect_n, "exact": indirect_hit},
        "pred_counts": dict(Counter(row.get("speech_act") for row in pred)),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
