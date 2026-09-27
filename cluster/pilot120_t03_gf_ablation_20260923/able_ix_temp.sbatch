#!/usr/bin/env bash
# ABLE IX: one Goal-First temperature, five-run set (keep seed 0 if present; emit 1-4).
# Intent = automatic Jaccard screen, not official two-judge. Keep every seed.
#SBATCH --job-name=p120-able-txx
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=2-12:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109,mscluster111
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-able-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-able-%j.err

set -euo pipefail
umask 077

: "${T03_CODE_ROOT:?}"
: "${ABLE_OUTPUT:?}"
: "${ABLE_TEMP:?}"
: "${GFV2_CONTAINER:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"
: "${PRIO_OUT:=/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915}"

CODE="${T03_CODE_ROOT}"
OUT="${ABLE_OUTPUT}"
TAG="T${ABLE_TEMP}"
EXP="${OUT}/${TAG}"
if [[ -n "${ABLE_SEEDS:-}" ]]; then
  read -r -a SEEDS <<< "${ABLE_SEEDS}"
else
  SEEDS=(1 2 3 4)
fi

mkdir -p "${EXP}" /home-mscluster/mbangie/t12-hpc/logs
cd "${CODE}"

GPU_USED=999999
for attempt in $(seq 1 18); do
  GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
  GPU_USED="${GPU_USED%% *}"
  GPU_USED="${GPU_USED:-999999}"
  echo "gpu_preflight attempt=${attempt} used_mib=${GPU_USED}"
  if [[ "${GPU_USED}" -le 1000 ]]; then
    break
  fi
  sleep 20
done
if [[ "${GPU_USED}" -gt 1000 ]]; then
  echo "busy_gpu:${GPU_USED}" >&2
  exit 42
fi

python3 scripts/evaluate_goal_first_manager_v2.py --help | grep -q -- '--temperature' \
  || { echo "stale_eval_script_missing_temperature" >&2; exit 2; }

ENV_CSV="PYTHONPATH=${CODE}/src:${GFV2_TRAINING_SITE_PACKAGES},HF_HOME=${GFV2_HF_HOME},HOME=${HOME},PATH=/usr/local/bin:/usr/bin:/bin"

qwen() {
  /usr/bin/apptainer exec --nv --cleanenv --env "${ENV_CSV}" \
    --bind "${CODE}:${CODE}" \
    --bind "${OUT}:${OUT}" \
    --bind "${PRIO_OUT}:${PRIO_OUT}" \
    --bind "${GFV2_HF_HOME}:${GFV2_HF_HOME}" \
    --bind "${GFV2_TRAINING_SITE_PACKAGES}:${GFV2_TRAINING_SITE_PACKAGES}" \
    "${GFV2_CONTAINER}" \
    python3 "$@"
}

count_jsonl() {
  local path="$1"
  if [[ ! -f "${path}" ]]; then echo 0; return; fi
  python3 -c "import pathlib; p=pathlib.Path('${path}'); print(sum(1 for line in p.read_text(encoding='utf-8').splitlines() if line.strip()))"
}

score_one() {
  local seed="$1"
  local pred="$2"
  local dest="$3"
  python3 scripts/score_gf_temp_ablation_20260923.py \
    --root "${CODE}" \
    --pred "${pred}" \
    --out "${dest}" \
    --temperature "${ABLE_TEMP}" \
    --seed "${seed}" \
    --label "goal_first_${TAG}_seed${seed}"
}

# Import existing unified seed 0 (do not re-emit).
SEED0_SRC="${PRIO_OUT}/${TAG}/predictions/goal_first_manager_v2.predictions.jsonl"
SEED0_DIR="${EXP}/seed_0"
if [[ "$(count_jsonl "${SEED0_SRC}")" -ge 120 ]]; then
  mkdir -p "${SEED0_DIR}/predictions"
  if [[ ! -f "${SEED0_DIR}/predictions/goal_first_manager_v2.predictions.jsonl" ]]; then
    cp -f "${SEED0_SRC}" "${SEED0_DIR}/predictions/goal_first_manager_v2.predictions.jsonl"
    cp -f "${PRIO_OUT}/${TAG}/run_manifest.json" "${SEED0_DIR}/run_manifest.json" || true
  fi
  score_one 0 "${SEED0_DIR}/predictions/goal_first_manager_v2.predictions.jsonl" "${SEED0_DIR}/score.json"
  echo "imported_seed0_${TAG}"
else
  echo "missing_seed0_${TAG}" >&2
fi

echo "ABLE_IX ${TAG} emit seeds=${SEEDS[*]}"
for SEED in "${SEEDS[@]}"; do
  TDIR="${EXP}/seed_${SEED}"
  PRED="${TDIR}/predictions/goal_first_manager_v2.predictions.jsonl"
  mkdir -p "${TDIR}/predictions"
  if [[ "$(count_jsonl "${PRED}")" -ge 120 ]]; then
    echo "skip_complete_${TAG}_seed_${SEED}"
  else
    echo "emitting_${TAG}_seed_${SEED}"
    qwen scripts/evaluate_goal_first_manager_v2.py \
      --root "${CODE}" \
      --output-dir "${TDIR}" \
      --temperature "${ABLE_TEMP}" \
      --seed "${SEED}"
  fi
  score_one "${SEED}" "${PRED}" "${TDIR}/score.json"
  echo "scored_${TAG}_seed_${SEED}"
done

python3 scripts/aggregate_able_ix_means_20260923.py \
  --root "${OUT}" \
  --out "${OUT}/ABLE_IX_FIVE_SEED_SUMMARY.json"

echo "ABLE_IX_TEMP_DONE ${TAG}"
printf 'temp\t%s\tout\t%s\n' "${ABLE_TEMP}" "${EXP}" | tee "${EXP}/run_complete.tsv"
