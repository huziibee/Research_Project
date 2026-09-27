#!/usr/bin/env bash
# CPU audit of goal-first v2 replica-1 as soon as job 53074 finishes.
# Runs on bigbatch so it does not compete with GPU follow-on 53081.
#SBATCH --job-name=gf-v2-r1-audit
#SBATCH --partition=bigbatch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/gf-v2-r1-audit-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/gf-v2-r1-audit-%j.err

set -euo pipefail
umask 077
: "${GFV2_CODE_ROOT:?}"
: "${GFV2_R1_MANAGER_DIR:?}"
: "${GFV2_R1_AUDIT_OUT:?}"

cd "${GFV2_CODE_ROOT}"
mkdir -p "$(dirname "${GFV2_R1_AUDIT_OUT}")"

# Wait until predictions are complete (53074 may still be writing evals at exit edge).
for i in $(seq 1 60); do
  n=$(wc -l < "${GFV2_R1_MANAGER_DIR}/predictions/goal_first_manager_v2.predictions.jsonl" 2>/dev/null || echo 0)
  if [[ "${n}" -ge 120 ]] && [[ -f "${GFV2_R1_MANAGER_DIR}/evaluations/goal_first_manager_v2.eval.json" ]]; then
    break
  fi
  sleep 30
done

python3 scripts/audit_goal_first_v2_predictions.py \
  --manager-dir "${GFV2_R1_MANAGER_DIR}" \
  --out "${GFV2_R1_AUDIT_OUT}" \
  --expected-rows 120
