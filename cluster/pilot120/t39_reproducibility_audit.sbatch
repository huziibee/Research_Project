#!/bin/bash
# Final CPU-only R1--R5 hash audit; non-identical greedy replay hashes are a VERIFY_FAILED result.
#SBATCH --job-name=p120-t39-repro-audit
#SBATCH --partition=bigbatch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-t39-repro-audit-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-t39-repro-audit-%j.err

set -euo pipefail
umask 077
: "${T39_CODE_ROOT:?}"
: "${T39_TRAINING_SITE_PACKAGES:?}"
: "${T39_CONTAINER:?}"
: "${T39_OUTPUT_ROOT:?}"
cd "${T39_CODE_ROOT}"

exec /usr/bin/apptainer exec --cleanenv \
  --env "PYTHONPATH=${T39_TRAINING_SITE_PACKAGES}:${T39_CODE_ROOT}/src" \
  "${T39_CONTAINER}" \
  python3 scripts/pilot120_t39_evidence.py \
  --root "${T39_CODE_ROOT}" \
  --policy "${T39_CODE_ROOT}/configs/evaluation/pilot120_early_analysis_policy_v1.json" \
  --analysis-policy "${T39_CODE_ROOT}/configs/evaluation/pilot120_t39_evidence_policy_v1.json" \
  reproducibility \
  --replica-evidence "R1=${T39_OUTPUT_ROOT}/R1/t39_evidence_atlas.json" \
  --replica-evidence "R2=${T39_OUTPUT_ROOT}/R2/t39_evidence_atlas.json" \
  --replica-evidence "R3=${T39_OUTPUT_ROOT}/R3/t39_evidence_atlas.json" \
  --replica-evidence "R4=${T39_OUTPUT_ROOT}/R4/t39_evidence_atlas.json" \
  --replica-evidence "R5=${T39_OUTPUT_ROOT}/R5/t39_evidence_atlas.json" \
  --output "${T39_OUTPUT_ROOT}/t39_reproducibility_audit.json"
