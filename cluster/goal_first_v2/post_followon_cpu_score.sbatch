#!/usr/bin/env bash
# CPU scoring after follow-on job 53081 completes (R2/R3 + natives).
#SBATCH --job-name=gf-followon-score
#SBATCH --partition=bigbatch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/gf-followon-score-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/gf-followon-score-%j.err

set -euo pipefail
umask 077
: "${GFV2_CODE_ROOT:?}"
: "${FOLLOWON_OUTPUT:?}"
: "${FOLLOWON_SCORE_OUT:?}"

cd "${GFV2_CODE_ROOT}"
mkdir -p "${FOLLOWON_SCORE_OUT}"

python3 scripts/score_goal_first_followon_cpu_20260911.py \
  --code-root "${GFV2_CODE_ROOT}" \
  --followon-root "${FOLLOWON_OUTPUT}" \
  --out "${FOLLOWON_SCORE_OUT}"
