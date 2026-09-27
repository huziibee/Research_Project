#!/usr/bin/env python3
import json
from pathlib import Path
from collections import Counter

p = Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_capability_debate-20260918/capability_judge/capability_judgments.jsonl")
rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
print("n", len(rows), "failed", sum(1 for r in rows if r.get("failed")))
print("errors", Counter(r.get("error") for r in rows))
for i in (0, 5, 20):
    r = rows[i]
    print("---", r["record_id"], "err=", r.get("error"))
    print("attempts", r.get("attempts"))
    raw = r.get("raw_output") or ""
    print("raw_len", len(raw))
    print(raw[:1200])
    print()
