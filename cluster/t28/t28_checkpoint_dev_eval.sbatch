#!/bin/bash
# Resumable T28 source-dev evaluation under frozen T27F task contracts.
# Uses task prompts + LMFE constrained decoding; not Pilot-120 / full T12 envelope.
# Exclude weak/old biggpus (106–109). mscluster107/108 reject unprivileged Apptainer
# user-namespace mappings (setgroups permission denied; jobs 30609/30610 on 108).
# cpus-per-task=12 matches mscluster110/111 capacity (12 CPUs).
#SBATCH --job-name=t28-dev-eval
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=3-00:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
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
: "${T28_CONTAINER:?}"
# Optional subset/smoke knobs (space-separated argv fragment), e.g.:
# T28_EVAL_EXTRA_ARGS='--task-ids predict_ambiguity_v1 --limit 48 --adapter-scale 0.35'
T28_EVAL_EXTRA_ARGS="${T28_EVAL_EXTRA_ARGS:-}"
cd "${T28_CODE_ROOT}"
T28_DEV_MANIFEST="${T28_BUNDLE_ROOT}/outputs/t28_r3/frozen_manifests/source_dev_task_manifest.jsonl"
if [[ ! -r "${T28_DEV_MANIFEST}" ]]; then
  echo "T28 frozen source-dev manifest is unreadable: ${T28_DEV_MANIFEST}" >&2
  exit 64
fi

# shellcheck disable=SC2086
exec /usr/bin/apptainer exec --nv --cleanenv --env "PYTHONPATH=${T28_TRAINING_SITE_PACKAGES}:${T28_CODE_ROOT}/src,HF_HOME=${T28_HF_HOME},HUGGINGFACE_HUB_CACHE=${T28_HF_HOME}/hub,TRANSFORMERS_CACHE=${T28_HF_HOME}/hub,T28_TRAINING_SITE_PACKAGES=${T28_TRAINING_SITE_PACKAGES}" "${T28_CONTAINER}" \
  python scripts/evaluate_t28_checkpoint_dev.py \
  --bundle-root "${T28_BUNDLE_ROOT}" \
  --dev-manifest "${T28_DEV_MANIFEST}" \
  --adapter "${T28_ADAPTER}" \
  --base-model Qwen/Qwen3-8B \
  --base-revision b968826d9c46dd6066d109eabc6255188de91218 \
  --output-dir "${T28_EVAL_OUTPUT}" \
  ${T28_EVAL_EXTRA_ARGS}
