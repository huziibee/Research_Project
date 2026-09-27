#!/usr/bin/env bash
# One-shot verification of unblock readiness. No long waits.
set -euo pipefail
umask 077

echo "=== QUEUE ==="
squeue -u mbangie || true
echo

echo "=== R1 MANIFEST ==="
python3 - <<'PY'
import json
from pathlib import Path
p = Path("/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911/manager/run_manifest.json")
m = json.loads(p.read_text(encoding="utf-8"))
print("status", m.get("status"))
print("row_failure_total", m.get("row_failure_total"))
print("soft_pass_note", m.get("soft_pass_note"))
print("validation", json.dumps(m.get("validation"), sort_keys=True))
PY
echo

echo "=== CLUSTER CODE ==="
python3 - <<'PY'
from pathlib import Path
eval_p = Path("/home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911/scripts/evaluate_goal_first_manager_v2.py")
anal_p = Path("/home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911/src/ambiguity_manager/systems/goal_first_analysis_v2.py")
comb = Path("/home-mscluster/mbangie/t12-hpc/code/followon-native-20260911/cluster/followon_53074/combined.sbatch")
clara = Path("/home-mscluster/mbangie/t12-hpc/code/followon-native-20260911/cluster/followon_53074/clara_dedicated.sbatch")
e = eval_p.read_text(encoding="utf-8")
a = anal_p.read_text(encoding="utf-8")
c = comb.read_text(encoding="utf-8")
checks = {
    "eval_exists": eval_p.exists(),
    "VERIFY_PASSED_WITH_ROW_FAILURES": "VERIFY_PASSED_WITH_ROW_FAILURES" in e,
    "exit0_startswith_VERIFY_PASSED": 'startswith("VERIFY_PASSED")' in e,
    "repetition_penalty": "repetition_penalty=1.08" in e,
    "no_repeat_ngram_size": "no_repeat_ngram_size=4" in e,
    "route_softened": "silently[ _-]?" in a and r"\broute\b(?!" in a,
    "combined_exists": comb.exists(),
    "clara_in_packets": '("clara"' in c or "(\"clara\"" in c or '"clara", "clara.jsonl"' in c,
    "native_task_required_True": '"required": True' in c and "min_remaining_seconds\": 7200 if task == \"clara\"" in c,
    "clara_dedicated_exists": clara.exists(),
}
for k, v in checks.items():
    print(f"{k}\t{v}")
print("ALL_CODE_OK", all(checks.values()))
PY
echo

echo "=== RESULTS DIRS ==="
ls -1 /home-mscluster/mbangie/t12-hpc/results/ | grep -E 'followon|clara|goal_first' || true
for f in \
  /home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b/submission_chain.tsv \
  /home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912/submission.tsv \
  /home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260911/submission.tsv
do
  if [[ -f "$f" ]]; then
    echo "FOUND $f"
    cat "$f"
  fi
done

echo
echo "=== JOB DETAILS (followon/clara/repair if queued) ==="
for jid in $(squeue -u mbangie -h -o '%i' 2>/dev/null || true); do
  echo "--- job $jid ---"
  scontrol show job "$jid" | tr ' ' '\n' | grep -E '^(JobId|JobName|JobState|Reason|Dependency|Command|WorkDir)=' || true
done
