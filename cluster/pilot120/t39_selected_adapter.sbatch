#!/bin/bash
# One fresh selected-adapter replay. Pair comparison is deliberately CPU-only.
#SBATCH --job-name=p120-t39-adapter
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=02:00:00
#SBATCH --nodelist=mscluster[110,112]
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-t39-adapter-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-t39-adapter-%j.err

set -euo pipefail
umask 077
: "${T39_CODE_ROOT:?}"
: "${T39_TRAINING_SITE_PACKAGES:?}"
: "${T39_HF_HOME:?}"
: "${T39_CONTAINER:?}"
: "${T39_COMPONENT_OUTPUT:?}"
: "${T39_SELECTED_ADAPTER:?}"
: "${T39_ADAPTER_IDENTITY:?}"
: "${T39_ADAPTER_SCALE:?}"
: "${T39_REPLICATE:?}"
: "${T39_CODE_COMMIT:?}"
: "${T39_CONTAINER_SHA256:?}"
: "${T39_MODEL_SNAPSHOT:?}"
: "${T39_EXECUTION_CONTRACT:?}"
cd "${T39_CODE_ROOT}"

/usr/bin/apptainer exec --nv --cleanenv \
  --env "PYTHONPATH=${T39_TRAINING_SITE_PACKAGES}:${T39_CODE_ROOT}/src,T39_CODE_ROOT=${T39_CODE_ROOT},T39_CODE_COMMIT=${T39_CODE_COMMIT},T39_CONTAINER=${T39_CONTAINER},T39_CONTAINER_SHA256=${T39_CONTAINER_SHA256},T39_SLURM_JOB_ID=${SLURM_JOB_ID:-unknown},T39_SLURMD_NODENAME=${SLURMD_NODENAME:-unknown}" \
  "${T39_CONTAINER}" \
  python3 scripts/pilot120_t39_runtime_provenance.py \
  verify-component \
  --root "${T39_CODE_ROOT}" \
  --container "${T39_CONTAINER}" \
  --adapter "${T39_SELECTED_ADAPTER}" \
  --adapter-identity "${T39_ADAPTER_IDENTITY}" \
  --model-snapshot "${T39_MODEL_SNAPSHOT}" \
  --code-commit "${T39_CODE_COMMIT}" \
  --contract "${T39_EXECUTION_CONTRACT}" \
  --component selected_adapter \
  --replicate-id "${T39_REPLICATE}" \
  --output "${T39_COMPONENT_OUTPUT}/runtime/t39_runtime_provenance.${SLURM_JOB_ID}.json"

exec /usr/bin/apptainer exec --nv --cleanenv \
  --env "PYTHONPATH=${T39_TRAINING_SITE_PACKAGES}:${T39_CODE_ROOT}/src,HF_HOME=${T39_HF_HOME},HUGGINGFACE_HUB_CACHE=${T39_HF_HOME}/hub,TRANSFORMERS_CACHE=${T39_HF_HOME}/hub" \
  "${T39_CONTAINER}" \
  python3 scripts/evaluate_pilot_120_direct_base.py \
  --root "${T39_CODE_ROOT}" \
  --output-dir "${T39_COMPONENT_OUTPUT}" \
  --system-id t28_selected_adapter_llm \
  --adapter "${T39_SELECTED_ADAPTER}" \
  --adapter-identity "${T39_ADAPTER_IDENTITY}" \
  --adapter-scale "${T39_ADAPTER_SCALE}"
