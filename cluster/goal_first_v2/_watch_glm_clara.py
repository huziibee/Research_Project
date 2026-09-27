#!/usr/bin/env python3
from pathlib import Path
import subprocess
import time

root = Path("/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b")
clara = root / "native" / "glm47" / "clara"
pred = clara / "predictions.jsonl"
log = clara / "server.log"
gemma = root / "native" / "gemma4" / "clara" / "predictions.jsonl"
print("=== QUEUE ===")
print(subprocess.check_output(["squeue", "-u", "mbangie", "-o", "%i %T %M %N %r"], text=True))
print(subprocess.check_output(["sacct", "-j", "53188,53191,53192", "--format=JobID,JobName%22,State,ExitCode,Elapsed,NodeList", "-X"], text=True))
text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
print("glm_clara_posts", text.count("POST /v1/chat/completions HTTP/1.1"))
if log.exists():
    print("glm_clara_log_size", log.stat().st_size, "age_s", round(time.time() - log.stat().st_mtime, 1))
print("glm_clara_pred_exists", pred.exists())
if pred.exists():
    print("glm_clara_rows", sum(1 for line in pred.open(encoding="utf-8") if line.strip()))
if gemma.exists():
    print("gemma_clara_rows", sum(1 for line in gemma.open(encoding="utf-8") if line.strip()))
native = root / "native"
if native.exists():
    for p in sorted(native.rglob("predictions.jsonl")):
        n = sum(1 for line in p.open(encoding="utf-8") if line.strip())
        print("native", p.relative_to(root), n)
