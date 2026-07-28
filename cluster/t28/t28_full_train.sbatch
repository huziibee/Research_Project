#!/bin/bash
# T28 production profile: one whole Blackwell node, no Slurm GPU GRES.
#SBATCH --job-name=t28-full-train
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=24:00:00
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/t28-full-train-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/t28-full-train-%j.err

set -euo pipefail
umask 077
: "${T28_RUN_ID:?T28_RUN_ID is required}"
: "${T28_OUTPUT_DIR:?T28_OUTPUT_DIR is required}"
: "${T28_BUNDLE_ROOT:?T28_BUNDLE_ROOT is required}"
: "${T28_SOURCE_COMMIT:?T28_SOURCE_COMMIT is required}"
: "${T28_CODE_ROOT:?T28_CODE_ROOT is required}"
: "${T28_TRAINING_SITE_PACKAGES:?T28_TRAINING_SITE_PACKAGES is required}"
: "${T28_HF_HOME:?T28_HF_HOME is required}"
cd "${T28_CODE_ROOT}"

/usr/bin/nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader
/usr/bin/python3 - <<'PY'
import os, shutil
ram = shutil.disk_usage('/').free
print({'node': os.uname().nodename, 'python': os.sys.version, 'free_root_bytes': ram})
PY

test "$(hostname)" != ""
test -d "${T28_OUTPUT_DIR}"
test "$(df -Pk "${T28_OUTPUT_DIR}" | awk 'NR==2 {print $4}')" -ge 524288000

# The frozen environment/container is supplied by the submission wrapper.
if [[ -n "${T28_CONTAINER:-}" ]]; then
  exec /usr/bin/apptainer exec --nv --cleanenv --env "PYTHONPATH=${T28_TRAINING_SITE_PACKAGES}:${T28_CODE_ROOT}/src,HF_HOME=${T28_HF_HOME},HUGGINGFACE_HUB_CACHE=${T28_HF_HOME}/hub,TRANSFORMERS_CACHE=${T28_HF_HOME}/hub" "${T28_CONTAINER}" \
    python scripts/train_t28_full.py --training-plan "${T28_BUNDLE_ROOT}/configs/model/t28_training_plan_v1.json" --run-matrix "${T28_BUNDLE_ROOT}/configs/model/t28_frozen_run_matrix_v1.json" --permitted-view "${T28_BUNDLE_ROOT}/data/processed/weak_pool/t28_permitted_train_dev.jsonl" --canonical-corpus "${T28_BUNDLE_ROOT}/data/processed/weak_pool/weak_pool_canonical.jsonl" --train-manifest "${T28_BUNDLE_ROOT}/outputs/t28_r3/frozen_manifests/source_train_task_manifest.jsonl" --dev-manifest "${T28_BUNDLE_ROOT}/outputs/t28_r3/frozen_manifests/source_dev_task_manifest.jsonl" --base-model Qwen/Qwen3-8B --base-revision b968826d9c46dd6066d109eabc6255188de91218 --schema-registry "${T28_BUNDLE_ROOT}/configs/model/evidence/t27f_schema_preflight_live.json" --seed 20260728 --bundle-root "${T28_BUNDLE_ROOT}" --run-id "${T28_RUN_ID}" --source-commit "${T28_SOURCE_COMMIT}" --output-dir "${T28_OUTPUT_DIR}" --result-dir "${T28_OUTPUT_DIR}"
fi
exec python scripts/train_t28_full.py --training-plan "${T28_BUNDLE_ROOT}/configs/model/t28_training_plan_v1.json" --run-matrix "${T28_BUNDLE_ROOT}/configs/model/t28_frozen_run_matrix_v1.json" --permitted-view "${T28_BUNDLE_ROOT}/data/processed/weak_pool/t28_permitted_train_dev.jsonl" --canonical-corpus "${T28_BUNDLE_ROOT}/data/processed/weak_pool/weak_pool_canonical.jsonl" --train-manifest "${T28_BUNDLE_ROOT}/outputs/t28_r3/frozen_manifests/source_train_task_manifest.jsonl" --dev-manifest "${T28_BUNDLE_ROOT}/outputs/t28_r3/frozen_manifests/source_dev_task_manifest.jsonl" --base-model Qwen/Qwen3-8B --base-revision b968826d9c46dd6066d109eabc6255188de91218 --schema-registry "${T28_BUNDLE_ROOT}/configs/model/evidence/t27f_schema_preflight_live.json" --seed 20260728 --bundle-root "${T28_BUNDLE_ROOT}" --run-id "${T28_RUN_ID}" --source-commit "${T28_SOURCE_COMMIT}" --output-dir "${T28_OUTPUT_DIR}" --result-dir "${T28_OUTPUT_DIR}"
