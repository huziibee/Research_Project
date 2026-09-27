#!/bin/bash
#SBATCH --job-name=p120-fix-emit
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=1-00:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-fix-emit-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-fix-emit-%j.err

set -euo pipefail
umask 077

: "${FIX_CODE_ROOT:?}"
: "${FIX_OUTPUT:?}"
: "${GFV2_CONTAINER:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"

CODE="${FIX_CODE_ROOT}"
OUT="${FIX_OUTPUT}"
mkdir -p "${OUT}" /home-mscluster/mbangie/t12-hpc/logs

GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
GPU_USED="${GPU_USED%% *}"
if [[ "${GPU_USED}" -gt 1000 ]]; then
  echo "busy_gpu:${GPU_USED}" >&2
  exit 42
fi

ENV_CSV="PYTHONPATH=${CODE}/src:${GFV2_TRAINING_SITE_PACKAGES},HF_HOME=${GFV2_HF_HOME},HOME=${HOME},PATH=/usr/local/bin:/usr/bin:/bin"

qwen() {
  /usr/bin/apptainer exec --nv --cleanenv --env "${ENV_CSV}" \
    --bind "${CODE}:${CODE}" \
    --bind "${OUT}:${OUT}" \
    --bind "${GFV2_HF_HOME}:${GFV2_HF_HOME}" \
    --bind "${GFV2_TRAINING_SITE_PACKAGES}:${GFV2_TRAINING_SITE_PACKAGES}" \
    "${GFV2_CONTAINER}" \
    python3 "$@"
}

# Temperature 0.7 = study default; also emit 0.0 for continuity with prior tables.
for TEMP in 0.7 0.0; do
  TDIR="${OUT}/T${TEMP}"
  mkdir -p "${TDIR}/predictions" "${TDIR}/scores"
  cd "${CODE}"
  qwen scripts/evaluate_goal_first_manager_v2.py \
    --root "${CODE}" \
    --output-dir "${TDIR}" \
    --temperature "${TEMP}" \
    --seed 0
  python3 scripts/score_official_sidecar_followon.py \
    --out "${TDIR}/scores/official_sidecar.json" \
    --search-root "${TDIR}"
done

echo FIX_EMIT_DONE
