#!/usr/bin/env bash
# Lightweight GLM CLARA / 53188 watch. Do not scancel 53188.
set -euo pipefail
OUT=/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b
echo "=== QUEUE ==="
squeue -u mbangie || true
echo
echo "=== SACCT ==="
sacct -j 53188,53191,53192 --format=JobID,JobName%22,State,ExitCode,Elapsed,NodeList -X || true
echo
echo "=== NATIVE COUNTS ==="
python3 - <<'PY'
from pathlib import Path
import os, time
root = Path("/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b")
now = time.time()
for p in sorted((root / "native").rglob("*")):
    if p.name in {"predictions.jsonl", "run_manifest.json", "server.log"}:
        n = ""
        if p.name == "predictions.jsonl":
            n = f" rows={sum(1 for line in p.open(encoding='utf-8') if line.strip())}"
        age = now - p.stat().st_mtime
        print(f"{p.relative_to(root)} size={p.stat().st_size}{n} age_s={age:.0f}")
print("--- task logs ---")
tl = root / "task_logs"
for p in sorted(tl.iterdir()):
    print(f"{p.name} size={p.stat().st_size} age_s={now-p.stat().st_mtime:.0f}")
print("--- glm clara stdout/err ---")
for name in ("glm47_clara.stdout.log", "glm47_clara.stderr.log"):
    p = tl / name
    if p.exists():
        text = p.read_text(encoding="utf-8", errors="replace")
        print(f"==== {name} ====")
        print(text[-800:] if text else "(empty)")
print("--- failed task stderr ---")
for name in ("gemma4_indirect.stderr.log", "glm47_ambik.stderr.log", "glm47_indirect.stderr.log"):
    p = tl / name
    if p.exists():
        print(f"==== {name} ====")
        print(p.read_text(encoding="utf-8", errors="replace"))
PY
echo
echo "=== GPU ==="
ssh -o BatchMode=yes -o ConnectTimeout=10 mscluster110 'nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,utilization.memory --format=csv,noheader; echo; ps -u mbangie -o pid,etime,pcpu,pmem,cmd --sort=-etime | head -n 20' || true
echo
echo "=== FOLLOWON OUT TAIL ==="
tail -n 15 /home-mscluster/mbangie/t12-hpc/logs/gf-followon-53188.out || true
echo "=== FOLLOWON ERR TAIL ==="
tail -n 15 /home-mscluster/mbangie/t12-hpc/logs/gf-followon-53188.err || true
