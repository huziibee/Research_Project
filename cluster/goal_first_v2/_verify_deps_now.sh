#!/usr/bin/env bash
set -euo pipefail
for jid in 53188 53189 53190 53191 53192; do
  echo "===== $jid ====="
  scontrol show job "$jid" | tr ' ' '\n' | grep -E '^(JobId|JobName|JobState|Reason|Dependency|Command)=' || echo "missing_job"
done
echo
echo "===== MANIFEST ====="
python3 - <<'PY'
import json
m = json.load(open("/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911/manager/run_manifest.json", encoding="utf-8"))
print("status", m.get("status"))
print("row_failure_total", m.get("row_failure_total"))
print("soft_pass_note", m.get("soft_pass_note"))
print("ordered", {k: v.get("ordered_complete") for k, v in (m.get("validation") or {}).items()})
PY
echo
echo "===== REPAIR SBATCH TARGET ====="
grep -n "GFV2_OUTPUT\|FOLLOWON\|output-dir\|repair" \
  /home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911/cluster/goal_first_v2/repair_failed.sbatch
echo
echo "===== CHAIN TSV ====="
cat /home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b/submission_chain.tsv
echo
echo "===== QUEUE ==="
squeue -u mbangie
echo
python3 - <<'PY'
from pathlib import Path
c = Path("/home-mscluster/mbangie/t12-hpc/code/followon-native-20260911/cluster/followon_53074/combined.sbatch").read_text(encoding="utf-8")
assert "7200 if task == \"clara\"" in c
assert '"required": True' in c
print("followon_clara_required_in_sbatch: YES")
print("paths:")
print("  followon=/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b")
print("  r1_manager=/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911/manager")
print("  clara_backup=/home-mscluster/mbangie/t12-hpc/results/clara_dedicated-20260912b")
PY
