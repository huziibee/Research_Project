#!/usr/bin/env bash
# CPU: official CPC F1 + risk-sensitive accuracy on whatever predictions exist.
#SBATCH --job-name=sidecar-score
#SBATCH --partition=bigbatch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/sidecar-score-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/sidecar-score-%j.err

set -euo pipefail
umask 077
: "${QWEN_NATIVE_CODE_ROOT:?}"
: "${SIDECAR_SCORE_OUT:?}"
: "${CLOSE_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/final_close-20260913}"
: "${SWEEP_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/temp_sweep-20260913}"

cd "${QWEN_NATIVE_CODE_ROOT}"
mkdir -p "${SIDECAR_SCORE_OUT}"
export PYTHONPATH="${QWEN_NATIVE_CODE_ROOT}/src:${QWEN_NATIVE_CODE_ROOT}/scripts${PYTHONPATH:+:${PYTHONPATH}}"

args=(--out "${SIDECAR_SCORE_OUT}/official_sidecar_followon.json")
if [[ -d "${CLOSE_OUTPUT}" ]]; then
  args+=(--search-root "${CLOSE_OUTPUT}")
fi
if [[ -d "${SWEEP_OUTPUT}" ]]; then
  args+=(--search-root "${SWEEP_OUTPUT}")
fi
python3 scripts/score_official_sidecar_followon.py "${args[@]}"
echo "sidecar_cpu_score_complete"
