#!/bin/bash
# T40 CPU-only inventory of unavailable interpretation gold; no annotation or inference.
#SBATCH --job-name=p120-t40-interp-audit
#SBATCH --partition=bigbatch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-t40-interp-audit-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-t40-interp-audit-%j.err

set -euo pipefail
umask 077
: "${T39_CODE_ROOT:?}"
: "${T39_TRAINING_SITE_PACKAGES:?}"
: "${T39_CONTAINER:?}"
: "${T39_EARLY_POLICY:?}"
: "${T39_ANALYSIS_POLICY:?}"
: "${T39_OUTPUT_ROOT:?}"
cd "${T39_CODE_ROOT}"

exec /usr/bin/apptainer exec --cleanenv \
  --env "PYTHONPATH=${T39_TRAINING_SITE_PACKAGES}:${T39_CODE_ROOT}/src" \
  "${T39_CONTAINER}" \
  python3 scripts/pilot120_t39_evidence.py \
  --root "${T39_CODE_ROOT}" \
  --policy "${T39_EARLY_POLICY}" \
  --analysis-policy "${T39_ANALYSIS_POLICY}" \
  interpretation-audit \
  --output "${T39_OUTPUT_ROOT}/t40_interpretation_requirements_audit.json"
