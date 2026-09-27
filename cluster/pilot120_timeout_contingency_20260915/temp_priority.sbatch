#!/usr/bin/env bash
# Priority order if mega times out: T0.7 (study default) → T1.0 → leftover T0.3.
# Skip any temperature dir that already has a complete goal_first prediction file.
#SBATCH --job-name=p120-temp-prio
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=2-00:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-temp-prio-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-temp-prio-%j.err

set -euo pipefail
umask 077

: "${PRIO_CODE_ROOT:?}"
: "${PRIO_OUTPUT:?}"
: "${GFV2_CONTAINER:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"
: "${MEGA_SWEEP_OUT:=/home-mscluster/mbangie/t12-hpc/results/temp_sweep-20260913}"

CODE="${PRIO_CODE_ROOT}"
OUT="${PRIO_OUTPUT}"
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
    --bind "${MEGA_SWEEP_OUT}:${MEGA_SWEEP_OUT}" \
    --bind "${GFV2_HF_HOME}:${GFV2_HF_HOME}" \
    --bind "${GFV2_TRAINING_SITE_PACKAGES}:${GFV2_TRAINING_SITE_PACKAGES}" \
    "${GFV2_CONTAINER}" \
    python3 "$@"
}

slice_done() {
  local temp="$1"
  local pred="${MEGA_SWEEP_OUT}/T${temp}/R1/goal_first_v2/predictions/goal_first_manager_v2.predictions.jsonl"
  local alt="${OUT}/T${temp}/predictions/goal_first_manager_v2.predictions.jsonl"
  if [[ -f "${pred}" ]]; then
    local n
    n="$(wc -l < "${pred}" | tr -d ' ')"
    [[ "${n}" -ge 120 ]] && return 0
  fi
  if [[ -f "${alt}" ]]; then
    local n
    n="$(wc -l < "${alt}" | tr -d ' ')"
    [[ "${n}" -ge 120 ]] && return 0
  fi
  return 1
}

# Priority: user-requested 0.5, study default 0.7, high 1.0, then finish mid 0.3 (0.0 already on mega).
for TEMP in 0.5 0.7 1.0 0.3; do
  if slice_done "${TEMP}"; then
    echo "skip_existing_T${TEMP}"
    continue
  fi
  TDIR="${OUT}/T${TEMP}"
  mkdir -p "${TDIR}/predictions"
  echo "emitting_priority_T${TEMP}"
  cd "${CODE}"
  qwen scripts/evaluate_goal_first_manager_v2.py \
    --root "${CODE}" \
    --output-dir "${TDIR}" \
    --temperature "${TEMP}" \
    --seed 0
  echo "done_priority_T${TEMP}"
done

echo TEMP_PRIORITY_DONE
