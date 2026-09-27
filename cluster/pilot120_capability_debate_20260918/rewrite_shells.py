#!/usr/bin/env python3
"""Rewrite cluster shell wrappers with Unix LF (no sed/tr)."""
from pathlib import Path

DEST = Path("/home-mscluster/mbangie/t12-hpc/code/pilot120_capability_debate-20260918/cluster/pilot120_capability_debate_20260918")

SUBMIT = r'''#!/usr/bin/env bash
# Submit capability-judge + debate pack after unified job (default afterany:55670).
set -euo pipefail
umask 077

: "${CAP_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/pilot120_capability_debate-20260918}"
: "${CAP_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/pilot120_capability_debate-20260918}"
: "${CAP_PREDICTIONS:=/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915/T0.7/predictions/goal_first_manager_v2.predictions.jsonl}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"
: "${AFTERANY:=55670}"

HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "${CAP_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs
export CAP_CODE_ROOT CAP_OUTPUT CAP_PREDICTIONS GFV2_CONTAINER GFV2_HF_HOME GFV2_TRAINING_SITE_PACKAGES

EXTRA=()
if [[ -n "${AFTERANY}" && "${AFTERANY}" != "0" && "${AFTERANY}" != "none" ]]; then
  EXTRA+=(--dependency="afterany:${AFTERANY}")
fi

jid=$(sbatch --parsable "${EXTRA[@]}" --export=ALL "${HERE}/capability_debate.sbatch")
echo "submitted_capability_debate ${jid} afterany=${AFTERANY}"
printf 'capability_debate\t%s\tafterany\t%s\tout\t%s\npred\t%s\n' \
  "${jid}" "${AFTERANY}" "${CAP_OUTPUT}" "${CAP_PREDICTIONS}" \
  | tee "${CAP_OUTPUT}/submission.tsv"
squeue -u mbangie
'''

SBATCH = r'''#!/usr/bin/env bash
# Capability LLM judge -> CPU re-route -> 2-debate + 1-adjudicate (reuse frozen intent).
#SBATCH --job-name=p120-cap-debate
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=1-00:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-cap-debate-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-cap-debate-%j.err

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
mkdir -p "${OUT}" /home-mscluster/mbangie/t12-hpc/logs
cd "${CODE}"

GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
GPU_USED="${GPU_USED%% *}"
if [[ "${GPU_USED}" -gt 1000 ]]; then
  echo "busy_gpu:${GPU_USED}" >&2
  exit 42
fi

test -f "${PRED}" || { echo "missing_predictions:${PRED}" >&2; exit 2; }
n_pred="$(wc -l < "${PRED}" | tr -d ' ')"
if [[ "${n_pred}" -lt 120 ]]; then
  echo "incomplete_predictions:${n_pred}" >&2
  exit 3
fi

python3 scripts/run_capability_llm_judge_20260918.py --help >/dev/null \
  || { echo "missing_capability_judge_script" >&2; exit 4; }
python3 scripts/run_ambiguity_debate_adjudicate_20260918.py --help >/dev/null \
  || { echo "missing_debate_script" >&2; exit 5; }

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

echo "=== STAGE 1: capability LLM judge (reuse intent) ==="
qwen scripts/run_capability_llm_judge_20260918.py \
  --root "${CODE}" \
  --predictions "${PRED}" \
  --output-dir "${OUT}/capability_judge" \
  --temperature 0.0 \
  --seed 0

echo "=== STAGE 2: CPU re-route with patched capability ==="
python3 scripts/reroute_patched_capability_20260918.py \
  --root "${CODE}" \
  --predictions "${PRED}" \
  --judgments "${OUT}/capability_judge/capability_judgments.jsonl" \
  --output-dir "${OUT}/capability_reroute" \
  --tag llm_capability

echo "=== STAGE 2b: oracle-gold upper bound (CPU) ==="
python3 scripts/reroute_patched_capability_20260918.py \
  --root "${CODE}" \
  --predictions "${PRED}" \
  --oracle-gold \
  --output-dir "${OUT}/capability_reroute" \
  --tag oracle_gold

echo "=== STAGE 3: 2-debate + 1-adjudicate + manager watch ==="
qwen scripts/run_ambiguity_debate_adjudicate_20260918.py \
  --root "${CODE}" \
  --predictions "${PRED}" \
  --capability-judgments "${OUT}/capability_judge/capability_judgments.jsonl" \
  --output-dir "${OUT}/ambiguity_debate" \
  --temperature 0.3 \
  --adjudicator-temperature 0.0 \
  --seed 0

echo CAP_DEBATE_DONE
printf 'pred\t%s\nout\t%s\n' "${PRED}" "${OUT}" | tee "${OUT}/run_complete.tsv"
'''

def write(name: str, text: str) -> None:
    path = DEST / name
    path.write_bytes(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))
    print(f"wrote {path} bytes={path.stat().st_size}")

write("submit.sh", SUBMIT)
write("capability_debate.sbatch", SBATCH)
print("ok")
