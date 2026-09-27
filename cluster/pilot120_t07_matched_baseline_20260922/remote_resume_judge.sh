#!/usr/bin/env bash
set -euo pipefail
T07=/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922
EXP=/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922/t07_matched_baseline_completion_20260922
REC=/home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922/one_turn_recovery_20260922

cp -f /tmp/run_blind_semantic_judge.py "${T07}/scripts/semantic_intent/run_blind_semantic_judge.py"
cp -f /tmp/t07_matched_baseline.sbatch \
  "${T07}/cluster/pilot120_t07_matched_baseline_20260922/t07_matched_baseline.sbatch"
chmod +x "${T07}/cluster/pilot120_t07_matched_baseline_20260922/t07_matched_baseline.sbatch"

echo "=== JUDGE COUNTS ==="
python3 - <<'PY'
from pathlib import Path
exp = Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922/t07_matched_baseline_completion_20260922")
for p in sorted((exp/"judges").rglob("*.jsonl")):
    n = sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())
    print(n, p)
PY

# Three empty-route clarify recovery cases (seed 0 other=3). Include, do not drop.
python3 - <<'PY'
import csv, json
from pathlib import Path
rec = Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922/one_turn_recovery_20260922")
exp = Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922/t07_matched_baseline_completion_20260922")
csv_path = rec / "07_per_case_results_seed0.csv"
rows = list(csv.DictReader(csv_path.open(encoding="utf-8"))) if csv_path.exists() else []
failed = []
for r in rows:
    to = (r.get("answered_terminal_route") or r.get("answered_route") or "").strip().lower()
    if not to or to in {"other", "missing", "none"}:
        failed.append(r)
# fallback: any row whose answered route is empty
if not failed:
    for r in rows:
        to = str(r.get("answered_terminal_route") or "")
        if to.strip() == "":
            failed.append(r)
out = {
    "note": "Three seed-0 clarify-recovery rows produced an empty terminal route (scored other). Kept in denominator; not dropped.",
    "n": len(failed),
    "cases": failed,
}
(exp / "CLARIFY_THREE_FAILED_CASES.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
md = ["# Three failed clarify-recovery cases (seed 0)", "", "Kept in the denominator. Not re-labelled and not dropped.", ""]
for r in failed:
    md.append(f"- `{r.get('record_id')}` answered_route=`{r.get('answered_terminal_route')}` first=`{r.get('first_turn_terminal_route')}`")
(exp / "CLARIFY_THREE_FAILED_CASES.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print("FAILED_CLARIFY", len(failed))
for r in failed:
    print(r.get("record_id"), r.get("answered_terminal_route"), r.get("first_turn_terminal_route"))
PY

if squeue -u mbangie -h | grep -E 'p120-t07' >/dev/null; then
  echo "t07_already_queued"
  squeue -u mbangie
  exit 0
fi

export T07_CODE_ROOT="${T07}"
export T07_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922
export GFV2_CONTAINER=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif
export GFV2_HF_HOME=/home-mscluster/mbangie/t12-hpc/hf-cache
export GFV2_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-hpc/training-site-packages
export A01_CONTAINER_SIF=/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif
export AFTERANY=0
export T07_GF_PREDS="${T07}/artifacts_t07/goal_first_manager_v2.predictions.jsonl"
export T07_BLIND_PREDS="${T07}/artifacts_t07/goal_first_context_blind_v2.predictions.jsonl"
export T07_DEGREE_PREDS="${T07}/artifacts_t07/degree_based_router_v2.predictions.jsonl"
export T07_TIMID_PREDS="${T07}/artifacts_t07/rich_conservative_manager_v2.predictions.jsonl"
bash "${T07}/cluster/pilot120_t07_matched_baseline_20260922/submit.sh"
echo RESUME_SUBMITTED
