#!/bin/bash
# Explicit non-protected T29/T30 early-results gate for the frozen Pilot-120.
#SBATCH --job-name=t29-t30-early-gate
#SBATCH --partition=bigbatch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/t29-t30-early-gate-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/t29-t30-early-gate-%j.err

set -euo pipefail
umask 077
: "${P120_CODE_ROOT:?}"
: "${P120_TRAINING_SITE_PACKAGES:?}"
: "${P120_CONTAINER:?}"
: "${P120_PAIRED_COMPARISON:?}"
: "${P120_CONSTANT_SUMMARY:?}"
: "${P120_MANAGER_SUMMARY:?}"
: "${T29_T30_EARLY_OUTPUT:?}"
cd "${P120_CODE_ROOT}"

exec /usr/bin/apptainer exec --cleanenv \
  --env "PYTHONPATH=${P120_TRAINING_SITE_PACKAGES}:${P120_CODE_ROOT}/src" \
  "${P120_CONTAINER}" \
  python scripts/t29_t30_early_results_gate.py \
  --paired-comparison "${P120_PAIRED_COMPARISON}" \
  --constant-summary "${P120_CONSTANT_SUMMARY}" \
  --manager-summary "${P120_MANAGER_SUMMARY}" \
  --output "${T29_T30_EARLY_OUTPUT}"
