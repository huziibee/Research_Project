#!/usr/bin/env bash
# Repair schema-failed rows on unified T0.5 / T0.7 (and T1.0 if present), then rescore sidecars.
# Also repair any failures left after 55670's fix-reemit of T0.0 / T0.3.
#SBATCH --job-name=p120-repair-rows
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=8:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-repair-rows-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-repair-rows-%j.err

set -euo pipefail
umask 077

: "${PRIO_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/pilot120_fix_emit-20260915}"
: "${PRIO_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"

CODE="${PRIO_CODE_ROOT}"
OUT="${PRIO_OUTPUT}"
cd "${CODE}"
mkdir -p /home-mscluster/mbangie/t12-hpc/logs

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

repair_temp() {
  local temp="$1"
  local tdir="${OUT}/T${temp}"
  if [[ ! -d "${tdir}/predictions" ]]; then
    echo "skip_missing_T${temp}"
    return 0
  fi
  echo "repair_pass1_T${temp}"
  qwen scripts/evaluate_goal_first_manager_v2.py \
    --root "${CODE}" --output-dir "${tdir}" \
    --temperature "${temp}" --seed 0 --repair-failed || true
  echo "repair_pass2_constrained_T${temp}"
  qwen scripts/evaluate_goal_first_manager_v2.py \
    --root "${CODE}" --output-dir "${tdir}" \
    --temperature "${temp}" --seed 0 --repair-failed --constrained-only || true
  mkdir -p "${tdir}/scores"
  python3 scripts/score_official_sidecar_followon.py \
    --out "${tdir}/scores/official_sidecar.json" \
    --search-root "${tdir}" || true
  echo "repair_done_T${temp}"
}

# Known failures today: T0.5 CA-0070/0211; T0.7 CA-0292/0963; T1.0 mid-fails; plus any 0.0/0.3 after reemit.
for TEMP in 0.5 0.7 1.0 0.0 0.3; do
  repair_temp "${TEMP}"
done

echo REPAIR_ROWS_DONE
