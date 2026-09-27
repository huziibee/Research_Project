#!/usr/bin/env bash
# GPU repair: regenerate only still-failed R1 rows in-place, then verify.
#SBATCH --job-name=gf-v2-repair
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=12:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/gf-v2-repair-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/gf-v2-repair-%j.err

set -euo pipefail
umask 077
: "${GFV2_CODE_ROOT:?}"
: "${GFV2_OUTPUT:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_CONTAINER:?}"

cd "${GFV2_CODE_ROOT}"
GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
if [[ "${GPU_USED}" -gt 1000 ]]; then
  echo "busy_gpu:${GPU_USED}" >&2
  exit 42
fi

export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
ENV="PYTHONPATH=${GFV2_TRAINING_SITE_PACKAGES}:${GFV2_CODE_ROOT}/src,HF_HOME=${GFV2_HF_HOME},HUGGINGFACE_HUB_CACHE=${GFV2_HF_HOME}/hub,TRANSFORMERS_CACHE=${GFV2_HF_HOME}/hub,HF_HUB_OFFLINE=1,TRANSFORMERS_OFFLINE=1"

CMD=(/usr/bin/apptainer exec --nv --cleanenv --env "${ENV}" "${GFV2_CONTAINER}"
  python3 scripts/evaluate_goal_first_manager_v2.py
  --root "${GFV2_CODE_ROOT}"
  --output-dir "${GFV2_OUTPUT}/manager"
  --repair-failed
  --max-new-tokens 6144
  --retry-max-new-tokens 8192
  --constrained-final-max-new-tokens 1536
)
if [[ -n "${GFV2_SELECTED_ADAPTER:-}" ]]; then
  CMD+=(--adapter "${GFV2_SELECTED_ADAPTER}" --adapter-identity "${GFV2_ADAPTER_IDENTITY}" --adapter-scale "${GFV2_ADAPTER_SCALE:-0.18}")
fi
exec "${CMD[@]}"
