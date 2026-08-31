#!/bin/bash
# CPU-only evidence/scoring step. It writes NOT_COMPUTED rather than masking a failed GPU component.
#SBATCH --job-name=p120-t39-evidence
#SBATCH --partition=bigbatch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-t39-evidence-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-t39-evidence-%j.err

set -euo pipefail
umask 077
: "${T39_CODE_ROOT:?}"
: "${T39_TRAINING_SITE_PACKAGES:?}"
: "${T39_CONTAINER:?}"
: "${T39_EARLY_POLICY:?}"
: "${T39_ANALYSIS_POLICY:?}"
: "${T39_REPLICATE_ROOT:?}"
: "${T39_REPLICATE:?}"
cd "${T39_CODE_ROOT}"

exec /usr/bin/apptainer exec --cleanenv \
  --env "PYTHONPATH=${T39_TRAINING_SITE_PACKAGES}:${T39_CODE_ROOT}/src" \
  "${T39_CONTAINER}" \
  python3 scripts/pilot120_t39_evidence.py \
  --root "${T39_CODE_ROOT}" \
  --policy "${T39_EARLY_POLICY}" \
  --analysis-policy "${T39_ANALYSIS_POLICY}" \
  evidence --allow-missing --require-runtime-provenance --replicate-id "${T39_REPLICATE}" \
  --prediction "direct_base_llm=${T39_REPLICATE_ROOT}/direct_base/direct_base_llm.predictions.jsonl" \
  --prediction "t28_selected_adapter_llm=${T39_REPLICATE_ROOT}/selected_adapter/t28_selected_adapter_llm.predictions.jsonl" \
  --prediction "degree_based_router=${T39_REPLICATE_ROOT}/manager/predictions/degree_based_router.predictions.jsonl" \
  --prediction "full_type_risk_aware_manager=${T39_REPLICATE_ROOT}/manager/predictions/full_type_risk_aware_manager.predictions.jsonl" \
  --prediction "context_blind_manager=${T39_REPLICATE_ROOT}/manager/predictions/context_blind_manager.predictions.jsonl" \
  --output "${T39_REPLICATE_ROOT}/t39_evidence_atlas.json"
