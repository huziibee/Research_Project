#!/usr/bin/env bash
# One-turn recovery (oracle upper bound) — Goal-First v2 + capability judge @ T0.7
#SBATCH --job-name=p120-1turn-rec
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=1-00:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109,mscluster111
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-1turn-rec-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-1turn-rec-%j.err

set -euo pipefail
umask 077

: "${REC_CODE_ROOT:?}"
: "${REC_OUTPUT:?}"
: "${GFV2_CONTAINER:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"

CODE="${REC_CODE_ROOT}"
OUT="${REC_OUTPUT}"
EXP="${OUT}/one_turn_recovery_20260922"
mkdir -p "${OUT}" "${EXP}" /home-mscluster/mbangie/t12-hpc/logs
cd "${CODE}"

GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
GPU_USED="${GPU_USED%% *}"
if [[ "${GPU_USED}" -gt 1000 ]]; then
  echo "busy_gpu:${GPU_USED}" >&2
  exit 42
fi

test -f "${EXP}/01_frozen_manifest.json" || { echo "missing_freeze:${EXP}" >&2; exit 2; }
test -f "${EXP}/04_oracle_responses.jsonl" || { echo "missing_oracles:${EXP}" >&2; exit 3; }
test -f "${CODE}/scripts/one_turn_recovery_20260922.py" || { echo "missing_script" >&2; exit 4; }

ENV_CSV="PYTHONPATH=${GFV2_TRAINING_SITE_PACKAGES}:${CODE}/src:${CODE}/scripts,HF_HOME=${GFV2_HF_HOME},HOME=${HOME},PATH=/usr/local/bin:/usr/bin:/bin"

qwen() {
  /usr/bin/apptainer exec --nv --cleanenv --env "${ENV_CSV}" \
    --bind "${CODE}:${CODE}" \
    --bind "${OUT}:${OUT}" \
    --bind "${GFV2_HF_HOME}:${GFV2_HF_HOME}" \
    --bind "${GFV2_TRAINING_SITE_PACKAGES}:${GFV2_TRAINING_SITE_PACKAGES}" \
    "${GFV2_CONTAINER}" \
    python3 "$@"
}

echo "=== PRECHECK: freeze asserts (CPU) ==="
python3 "${CODE}/scripts/one_turn_recovery_20260922.py" freeze \
  --evidence-root "${CODE}/evidence_pack_A" \
  --experiment-dir "${EXP}"

echo "=== GPU PREFLIGHT ==="
nvidia-smi || true
qwen - <<'PY'
import torch
print("torch", torch.__version__)
print("cuda_available", torch.cuda.is_available())
print("cuda_version", torch.version.cuda)
print("device_count", torch.cuda.device_count())
if not torch.cuda.is_available():
    raise SystemExit("cuda_preflight_failed")
print("gpu0", torch.cuda.get_device_name(0))
PY

echo "=== GPU RUN: control + answered, seeds 0 and 1 ==="
qwen scripts/one_turn_recovery_20260922.py run \
  --experiment-dir "${EXP}" \
  --temperature 0.7 \
  --seeds 0 1 \
  --max-clarify-depth 5

echo "=== SCORE (CPU safety recompute) ==="
python3 "${CODE}/scripts/one_turn_recovery_20260922.py" score \
  --experiment-dir "${EXP}" \
  --seeds 0 1

echo ONE_TURN_RECOVERY_DONE
printf 'out\t%s\nexp\t%s\n' "${OUT}" "${EXP}" | tee "${EXP}/run_complete.tsv"
