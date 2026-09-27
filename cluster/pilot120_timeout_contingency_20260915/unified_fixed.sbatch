#!/usr/bin/env bash
# Unified: new temps with fixes baked in, then re-emit already-done temps that lack fixes.
# Order: 0.5 → 0.7 → 1.0 → fix-reemit 0.0 → fix-reemit 0.3
# Each emit uses repaired CPC/ambiguity/clarification code; sidecar scored after each.
#SBATCH --job-name=p120-unified
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=2-12:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-unified-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-unified-%j.err

set -euo pipefail
umask 077

: "${PRIO_CODE_ROOT:?}"
: "${PRIO_OUTPUT:?}"
: "${GFV2_CONTAINER:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"

CODE="${PRIO_CODE_ROOT}"
OUT="${PRIO_OUTPUT}"
mkdir -p "${OUT}" /home-mscluster/mbangie/t12-hpc/logs
cd "${CODE}"

GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
GPU_USED="${GPU_USED%% *}"
if [[ "${GPU_USED}" -gt 1000 ]]; then
  echo "busy_gpu:${GPU_USED}" >&2
  exit 42
fi

# Prove local eval script accepts temperature (guards against stale cluster copy).
python3 scripts/evaluate_goal_first_manager_v2.py --help | grep -q -- '--temperature' \
  || { echo "stale_eval_script_missing_temperature" >&2; exit 2; }

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

emit_and_score() {
  local temp="$1"
  local tag="$2"
  local tdir="${OUT}/T${temp}"
  mkdir -p "${tdir}/predictions" "${tdir}/scores"
  local pred="${tdir}/predictions/goal_first_manager_v2.predictions.jsonl"
  if [[ -f "${pred}" ]]; then
    local n
    n="$(wc -l < "${pred}" | tr -d ' ')"
    if [[ "${n}" -ge 120 ]]; then
      echo "skip_complete_${tag}_T${temp}_n=${n}"
      python3 scripts/score_official_sidecar_followon.py \
        --out "${tdir}/scores/official_sidecar.json" \
        --search-root "${tdir}" || true
      return 0
    fi
  fi
  echo "emitting_${tag}_T${temp}"
  qwen scripts/evaluate_goal_first_manager_v2.py \
    --root "${CODE}" \
    --output-dir "${tdir}" \
    --temperature "${temp}" \
    --seed 0
  python3 scripts/score_official_sidecar_followon.py \
    --out "${tdir}/scores/official_sidecar.json" \
    --search-root "${tdir}" || true
  echo "done_${tag}_T${temp}"
}

# New / incomplete temps first (fixes already in CODE).
for TEMP in 0.5 0.7 1.0; do
  emit_and_score "${TEMP}" "priority"
done

# Re-emit already-finished mega temps with fix stack (wording/CPC/ambiguity).
for TEMP in 0.0 0.3; do
  emit_and_score "${TEMP}" "fix_reemit"
done

echo UNIFIED_DONE
