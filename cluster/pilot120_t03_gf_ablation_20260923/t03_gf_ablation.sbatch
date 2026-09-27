#!/usr/bin/env bash
# ABLE IX: Goal-First T=0.3 temperature ablation (route + automatic intent screen).
# Same fix-stack emit as unified T0.5/T0.7/T1.0. Pre-specified seeds only; keep every run.
#SBATCH --job-name=p120-t03-ableix
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=2-12:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109,mscluster111
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-t03-ableix-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-t03-ableix-%j.err

set -euo pipefail
umask 077

: "${T03_CODE_ROOT:?}"
: "${T03_OUTPUT:?}"
: "${GFV2_CONTAINER:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"

CODE="${T03_CODE_ROOT}"
OUT="${T03_OUTPUT}"
EXP="${OUT}/t03_gf_ablation_able_ix_20260923"
if [[ -n "${T03_SEEDS:-}" ]]; then
  read -r -a SEEDS <<< "${T03_SEEDS}"
else
  SEEDS=(1 2 3)
fi

mkdir -p "${EXP}" /home-mscluster/mbangie/t12-hpc/logs
cd "${CODE}"

GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
GPU_USED="${GPU_USED%% *}"
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

echo "ABLE_IX_T03 start seeds=${SEEDS[*]}"
for SEED in "${SEEDS[@]}"; do
  TDIR="${EXP}/seed_${SEED}"
  PRED="${TDIR}/predictions/goal_first_manager_v2.predictions.jsonl"
  mkdir -p "${TDIR}/predictions"
  if [[ "$(count_jsonl "${PRED}")" -ge 120 ]]; then
    echo "skip_complete_seed_${SEED}"
  else
    echo "emitting_T0.3_seed_${SEED}"
    qwen scripts/evaluate_goal_first_manager_v2.py \
      --root "${CODE}" \
      --output-dir "${TDIR}" \
      --temperature 0.3 \
      --seed "${SEED}"
  fi
  python3 scripts/score_gf_temp_ablation_20260923.py \
    --root "${CODE}" \
    --pred "${PRED}" \
    --out "${TDIR}/score.json" \
    --temperature 0.3 \
    --seed "${SEED}" \
    --label "goal_first_T0.3_seed${SEED}"
  echo "scored_seed_${SEED}"
done

python3 - <<PY
import json
from pathlib import Path
exp = Path("${EXP}")
rows = []
for seed_dir in sorted(exp.glob("seed_*")):
    score = seed_dir / "score.json"
    if score.exists():
        rows.append(json.loads(score.read_text(encoding="utf-8")))
summary = {
    "experiment": "ABLE_IX_T0.3_goal_first_ablation",
    "temperature": 0.3,
    "intent_metric": "automatic_jaccard_0.18_polarity_skip_not_official_two_judge",
    "retained_published_anchors": {
        "T0.5": {"route": 51, "intent_screen": 117},
        "T0.7": {"route": 56, "intent_screen": 118},
        "T1.0": {"route": 44, "intent_screen": 119},
    },
    "interpolation_note": (
        "Predicted descriptive pattern: T0.0 < T0.3 route < T0.5. "
        "All pre-specified seeds are retained. No run is discarded for not interpolating."
    ),
    "seeds": rows,
}
(exp / "FINAL_T03_ABLE_IX_SUMMARY.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2, sort_keys=True))
PY

echo T03_ABLE_IX_DONE
printf 'out\t%s\n' "${EXP}" | tee "${EXP}/run_complete.tsv"
