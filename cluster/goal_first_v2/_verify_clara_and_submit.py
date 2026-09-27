#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

root = Path("/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b")
print("=== VERIFY CLARA ===")
for system in ("gemma4", "glm47"):
    pred = root / "native" / system / "clara" / "predictions.jsonl"
    man = root / "native" / system / "clara" / "run_manifest.json"
    rows = [json.loads(line) for line in pred.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [row["record_id"] for row in rows]
    conds = sorted({row.get("condition") for row in rows})
    print(system, "rows", len(rows), "unique_ids", len(set(ids)), "conds", conds, "manifest", man.exists())
    if man.exists():
        print(" manifest", json.dumps(json.loads(man.read_text()), sort_keys=True)[:300])
print("=== 53192 / clara dedicated ===")
clara_out = Path("/home-mscluster/mbangie/t12-hpc/results/clara_dedicated-20260912b")
if clara_out.exists():
    for p in sorted(clara_out.rglob("*")):
        if p.is_file() and p.stat().st_size < 2_000_000:
            print(p, p.stat().st_size)
print("=== QUEUE BEFORE ===")
print(subprocess.check_output(["squeue", "-u", "mbangie"], text=True))
print(subprocess.check_output(["sacct", "-j", "53188,53191,53192", "--format=JobID,JobName%22,State,ExitCode,Elapsed,NodeList", "-X"], text=True))
