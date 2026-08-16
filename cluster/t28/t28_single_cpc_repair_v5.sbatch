#!/bin/bash
# Exact one-call T28 recovery with the enlarged thought budget already approved.
#SBATCH --job-name=t28-cpc-repair-v5
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=18:00:00
#SBATCH --nodelist=mscluster111
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109,mscluster112
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/t28-cpc-repair-v5-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/t28-cpc-repair-v5-%j.err

set -euo pipefail
umask 077
: "${T28_BUNDLE_ROOT:?}"
: "${T28_CODE_ROOT:?}"
: "${T28_TRAINING_SITE_PACKAGES:?}"
: "${T28_HF_HOME:?}"
: "${T28_CONTAINER:?}"
: "${T28_ADAPTER:?}"
: "${T28_EVAL_OUTPUT:?}"
cd "${T28_CODE_ROOT}"

exec /usr/bin/apptainer exec --nv --cleanenv \
  --env "PYTHONPATH=${T28_TRAINING_SITE_PACKAGES}:${T28_CODE_ROOT}/src,HF_HOME=${T28_HF_HOME},HUGGINGFACE_HUB_CACHE=${T28_HF_HOME}/hub,TRANSFORMERS_CACHE=${T28_HF_HOME}/hub,T28_TRAINING_SITE_PACKAGES=${T28_TRAINING_SITE_PACKAGES}" \
  "${T28_CONTAINER}" \
  python scripts/evaluate_t28_checkpoint_dev.py \
  --bundle-root "${T28_BUNDLE_ROOT}" \
  --dev-manifest "${T28_BUNDLE_ROOT}/outputs/t28_r3/frozen_manifests/source_dev_task_manifest.jsonl" \
  --adapter "${T28_ADAPTER}" \
  --base-model Qwen/Qwen3-8B \
  --base-revision b968826d9c46dd6066d109eabc6255188de91218 \
  --output-dir "${T28_EVAL_OUTPUT}" \
  --routing-eval \
  --call-ids-file configs/model/t28_cpc_clara1170_repair_call_ids_v1.txt \
  --adapter-scale 0.18 \
  --max-new-tokens-multiplier 12.8 \
  --repetition-penalty 1.08 \
  --no-repeat-ngram-size 4 \
  --decoder-bounds-config configs/model/t28_decoder_bounds_v4.json
