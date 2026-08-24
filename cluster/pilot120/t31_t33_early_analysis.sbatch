#!/bin/bash
# Hash-bound non-protected Pilot-120 early T31/T32/T33 analyses.
#SBATCH --job-name=p120-early-analysis
#SBATCH --partition=bigbatch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-early-analysis-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-early-analysis-%j.err

set -euo pipefail
umask 077
: "${P120_CODE_ROOT:?}"
: "${P120_TRAINING_SITE_PACKAGES:?}"
: "${P120_CONTAINER:?}"
: "${P120_EARLY_POLICY:?}"
: "${P120_T31PLUS_PREFLIGHT:?}"
: "${P120_T29_T30_GATE:?}"
: "${P120_EARLY_STAGE:?}"
: "${P120_EARLY_OUTPUT:?}"
cd "${P120_CODE_ROOT}"

args=(python3 scripts/pilot120_early_analysis.py --root "${P120_CODE_ROOT}" --policy "${P120_EARLY_POLICY}" --preflight "${P120_T31PLUS_PREFLIGHT}" --early-gate "${P120_T29_T30_GATE}")
case "${P120_EARLY_STAGE}" in
  t31)
    : "${P120_PREDICTION_ARGS:?}"
    # Intentional word splitting: each value is a prevalidated --prediction argument.
    args+=(cost ${P120_PREDICTION_ARGS} --output "${P120_EARLY_OUTPUT}")
    ;;
  t32)
    : "${P120_T31_OUTPUT:?}"
    args+=(paired --cost-input "${P120_T31_OUTPUT}" --output "${P120_EARLY_OUTPUT}")
    ;;
  t33)
    : "${P120_T31_OUTPUT:?}"; : "${P120_T32_OUTPUT:?}"
    args+=(ablations --cost-input "${P120_T31_OUTPUT}" --paired-input "${P120_T32_OUTPUT}" --output "${P120_EARLY_OUTPUT}")
    ;;
  *) echo "unknown P120_EARLY_STAGE=${P120_EARLY_STAGE}" >&2; exit 2 ;;
esac

exec /usr/bin/apptainer exec --cleanenv \
  --env "PYTHONPATH=${P120_TRAINING_SITE_PACKAGES}:${P120_CODE_ROOT}/src" \
  "${P120_CONTAINER}" "${args[@]}"
