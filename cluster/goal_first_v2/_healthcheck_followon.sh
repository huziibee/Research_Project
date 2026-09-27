#!/usr/bin/env bash
# Follow-on 53188 health check + auto scancel 53192 if CLARA complete.
set -euo pipefail
OUT=/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b
echo "=== QUEUE ==="
squeue -u mbangie || true
echo
echo "=== SACCT 53188 ==="
sacct -j 53188 --format=JobID,JobName%20,State,ExitCode,Elapsed,NodeList -X 2>/dev/null || true
echo
python3 <<'PY'
import json
from pathlib import Path
out = Path("/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b")
systems = [
    "goal_first_manager_v2",
    "rich_conservative_manager_v2",
    "degree_based_router_v2",
    "goal_first_context_blind_v2",
]

def pred_stats(rep: str):
    base = out / rep / "manager" / "predictions"
    if not base.exists():
        print(f"{rep}: predictions_dir_missing")
        return
    for sid in systems:
        p = base / f"{sid}.predictions.jsonl"
        if not p.exists():
            print(f"{rep}/{sid}: missing")
            continue
        rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        failed = [r["record_id"] for r in rows if r.get("failed") is True]
        print(f"{rep}/{sid}: n={len(rows)} failed={len(failed)} ids={failed[:8]}")
    man = out / rep / "manager" / "run_manifest.json"
    prog = out / rep / "manager" / "progress.json"
    if man.exists():
        m = json.loads(man.read_text())
        print(f"{rep} manifest status={m.get('status')} row_failure_total={m.get('row_failure_total')}")
    if prog.exists():
        print(f"{rep} progress={prog.read_text().strip()[:300]}")

for rep in ("R2", "R3"):
    pred_stats(rep)

native = out / "native"
if native.exists():
    for p in sorted(native.rglob("predictions.jsonl")):
        n = sum(1 for line in p.open(encoding="utf-8") if line.strip())
        print(f"native {p.relative_to(out)} rows={n}")
else:
    print("native: not_started")

tl = out / "task_logs"
if tl.exists():
    for p in sorted(tl.iterdir()):
        print(f"task_log {p.name} size={p.stat().st_size}")

# tasks status if runner writes one
for name in ("progress.json", "runner_state.json", "task_results.json"):
    p = out / name
    if p.exists():
        print(name, p.read_text()[:500])

# CLARA complete -> scancel backup
expected = 10444
ok = True
for system in ("gemma4", "glm47"):
    pred = out / "native" / system / "clara" / "predictions.jsonl"
    if not pred.is_file():
        ok = False
        break
    n = sum(1 for line in pred.open(encoding="utf-8") if line.strip())
    if n < expected:
        ok = False
        break
print("followon_clara_complete", ok)
if ok:
    import os
    os.system("scancel 53192")
    print("scanceled_53192")

# If a replica just finished with failures, print salvage hint (do not rewrite while RUNNING).
for rep in ("R2", "R3"):
    man = out / rep / "manager" / "run_manifest.json"
    if not man.exists():
        continue
    m = json.loads(man.read_text(encoding="utf-8"))
    status = str(m.get("status") or "")
    if status.startswith("VERIFY"):
        failed_n = 0
        for sid in systems:
            p = out / rep / "manager" / "predictions" / f"{sid}.predictions.jsonl"
            if not p.exists():
                continue
            failed_n += sum(1 for line in p.open(encoding="utf-8") if line.strip() and json.loads(line).get("failed") is True)
        print(f"{rep}_finished status={status} failed_rows={failed_n}")
        if failed_n:
            print(f"SALVAGE_HINT bash .../_salvage_followon_replica.sh {rep}")
PY
echo
echo "=== LOG TAIL ==="
tail -n 25 /home-mscluster/mbangie/t12-hpc/logs/gf-followon-53188.out 2>/dev/null || true
tail -n 15 /home-mscluster/mbangie/t12-hpc/logs/gf-followon-53188.err 2>/dev/null || true
