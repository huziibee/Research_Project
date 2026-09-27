#!/usr/bin/env bash
# CPU reparse debate (111/120) then GPU repair remaining IDs.
#SBATCH --job-name=p120-debate-fix
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=4:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-debate-fix-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-debate-fix-%j.err

set -euo pipefail
umask 077

: "${CAP_CODE_ROOT:?}"
: "${CAP_OUTPUT:?}"
: "${CAP_PREDICTIONS:?}"
: "${GFV2_CONTAINER:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"

CODE="${CAP_CODE_ROOT}"
OUT="${CAP_OUTPUT}"
PRED="${CAP_PREDICTIONS}"
cd "${CODE}"

GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
GPU_USED="${GPU_USED%% *}"
if [[ "${GPU_USED}" -gt 1000 ]]; then
  echo "busy_gpu:${GPU_USED}" >&2
  exit 42
fi

ENV_CSV="PYTHONPATH=${CODE}/src:${CODE}/scripts:${GFV2_TRAINING_SITE_PACKAGES},HF_HOME=${GFV2_HF_HOME},HOME=${HOME},PATH=/usr/local/bin:/usr/bin:/bin"

qwen() {
  /usr/bin/apptainer exec --nv --cleanenv --env "${ENV_CSV}" \
    --bind "${CODE}:${CODE}" \
    --bind "${OUT}:${OUT}" \
    --bind "$(dirname "${PRED}"):$(dirname "${PRED}")" \
    --bind "${GFV2_HF_HOME}:${GFV2_HF_HOME}" \
    --bind "${GFV2_TRAINING_SITE_PACKAGES}:${GFV2_TRAINING_SITE_PACKAGES}" \
    "${GFV2_CONTAINER}" \
    python3 "$@"
}

echo "=== CPU reparse debate raws ==="
python3 scripts/reparse_ambiguity_debate_20260918.py \
  --root "${CODE}" \
  --debate-jsonl "${OUT}/ambiguity_debate/ambiguity_debate_adjudication.jsonl" \
  --predictions "${PRED}" \
  --capability-judgments "${OUT}/capability_judge/capability_judgments.jsonl" \
  --output-dir "${OUT}/ambiguity_debate"

NEED="${OUT}/ambiguity_debate/need_gpu_repair.json"
n_need="$(python3 -c "import json;print(json.load(open('${NEED}'))['n'])")"
echo "need_gpu=${n_need}"
if [[ "${n_need}" -eq 0 ]]; then
  echo DEBATE_FIX_DONE_NO_GPU
  exit 0
fi

echo "=== GPU repair ${n_need} IDs ==="
qwen scripts/repair_ambiguity_debate_ids_20260918.py \
  --root "${CODE}" \
  --predictions "${PRED}" \
  --capability-judgments "${OUT}/capability_judge/capability_judgments.jsonl" \
  --debate-jsonl "${OUT}/ambiguity_debate/ambiguity_debate_adjudication.jsonl" \
  --ids-json "${NEED}" \
  --output-dir "${OUT}/ambiguity_debate" \
  --max-new-tokens 768 \
  --seed 1

# Final reparse/score pass for clean summary
python3 scripts/reparse_ambiguity_debate_20260918.py \
  --root "${CODE}" \
  --debate-jsonl "${OUT}/ambiguity_debate/ambiguity_debate_adjudication.jsonl" \
  --predictions "${PRED}" \
  --capability-judgments "${OUT}/capability_judge/capability_judgments.jsonl" \
  --output-dir "${OUT}/ambiguity_debate"

echo DEBATE_FIX_DONE
