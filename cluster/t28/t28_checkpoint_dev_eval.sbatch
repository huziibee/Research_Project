#!/bin/bash
# Resumable T28 source-dev evaluation from the preserved step-1500 adapter.
# Scientific inputs and decoding are frozen; this only changes batching and
# checkpointed evidence writes after the original 24-hour evaluation timeout.
#SBATCH --job-name=t28-dev-eval
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=24:00:00
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/t28-dev-eval-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/t28-dev-eval-%j.err

set -euo pipefail
umask 077
: "${T28_BUNDLE_ROOT:?}"
: "${T28_CODE_ROOT:?}"
: "${T28_TRAINING_SITE_PACKAGES:?}"
: "${T28_HF_HOME:?}"
: "${T28_ADAPTER:?}"
: "${T28_EVAL_OUTPUT:?}"
cd "${T28_CODE_ROOT}"

exec /usr/bin/apptainer exec --nv --cleanenv --env "PYTHONPATH=${T28_TRAINING_SITE_PACKAGES}:${T28_CODE_ROOT}/src,HF_HOME=${T28_HF_HOME},HUGGINGFACE_HUB_CACHE=${T28_HF_HOME}/hub,TRANSFORMERS_CACHE=${T28_HF_HOME}/hub" "${T28_CONTAINER}" \
  python scripts/evaluate_t28_checkpoint_dev.py \
  --bundle-root "${T28_BUNDLE_ROOT}" \
  --dev-manifest "${T28_BUNDLE_ROOT}/outputs/t28_r3/frozen_manifests/source_dev_task_manifest.jsonl" \
  --adapter "${T28_ADAPTER}" \
  --base-model Qwen/Qwen3-8B \
  --base-revision b968826d9c46dd6066d109eabc6255188de91218 \
  --output-dir "${T28_EVAL_OUTPUT}" \
  --batch-size 8 \
  --max-new-tokens 384
