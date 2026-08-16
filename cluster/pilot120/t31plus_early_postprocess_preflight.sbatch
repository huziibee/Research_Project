#!/bin/bash
# Hash-bound post-processing readiness record after the Pilot T29/T30 early gate.
#SBATCH --job-name=t31plus-early-preflight
#SBATCH --partition=bigbatch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/t31plus-early-preflight-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/t31plus-early-preflight-%j.err

set -euo pipefail
umask 077
: "${P120_CODE_ROOT:?}"
: "${P120_TRAINING_SITE_PACKAGES:?}"
: "${P120_CONTAINER:?}"
: "${T29_T30_EARLY_GATE:?}"
: "${T31PLUS_EARLY_PREFLIGHT_OUTPUT:?}"
cd "${P120_CODE_ROOT}"

exec /usr/bin/apptainer exec --cleanenv \
  --env "PYTHONPATH=${P120_TRAINING_SITE_PACKAGES}:${P120_CODE_ROOT}/src" \
  "${P120_CONTAINER}" \
  python scripts/t31plus_early_postprocess_preflight.py \
  --early-gate "${T29_T30_EARLY_GATE}" \
  --output "${T31PLUS_EARLY_PREFLIGHT_OUTPUT}"
