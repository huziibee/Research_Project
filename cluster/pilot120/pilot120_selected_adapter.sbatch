#!/bin/bash
# Pilot-120 selected-T28-adapter evaluation. Submitted only after T28_COMPLETE.
#SBATCH --job-name=p120-selected-adapter
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=12:00:00
#SBATCH --nodelist=mscluster111
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-selected-adapter-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-selected-adapter-%j.err

set -euo pipefail
umask 077
: "${P120_CODE_ROOT:?}"
: "${P120_TRAINING_SITE_PACKAGES:?}"
: "${P120_HF_HOME:?}"
: "${P120_CONTAINER:?}"
: "${P120_OUTPUT:?}"
: "${P120_SELECTED_ADAPTER:?}"
: "${P120_SELECTED_ADAPTER_IDENTITY:?}"
: "${P120_ADAPTER_SCALE:?}"
: "${P120_BASE_EVALUATION:?}"
: "${P120_BASE_PREDICTIONS:?}"
: "${P120_COMPARISON_OUTPUT:?}"
cd "${P120_CODE_ROOT}"

run_container() {
  /usr/bin/apptainer exec --nv --cleanenv \
    --env "PYTHONPATH=${P120_TRAINING_SITE_PACKAGES}:${P120_CODE_ROOT}/src,HF_HOME=${P120_HF_HOME},HUGGINGFACE_HUB_CACHE=${P120_HF_HOME}/hub,TRANSFORMERS_CACHE=${P120_HF_HOME}/hub" \
    "${P120_CONTAINER}" "$@"
}

run_container python scripts/evaluate_pilot_120_direct_base.py \
  --root "${P120_CODE_ROOT}" \
  --output-dir "${P120_OUTPUT}" \
  --system-id t28_selected_adapter_llm \
  --adapter "${P120_SELECTED_ADAPTER}" \
  --adapter-identity "${P120_SELECTED_ADAPTER_IDENTITY}" \
  --adapter-scale "${P120_ADAPTER_SCALE}"

run_container python scripts/compare_pilot_120_base_adapter.py \
  --root "${P120_CODE_ROOT}" \
  --base-evaluation "${P120_BASE_EVALUATION}" \
  --adapter-evaluation "${P120_OUTPUT}/t28_selected_adapter_llm.eval.json" \
  --base-predictions "${P120_BASE_PREDICTIONS}" \
  --adapter-predictions "${P120_OUTPUT}/t28_selected_adapter_llm.predictions.jsonl" \
  --output "${P120_COMPARISON_OUTPUT}"
