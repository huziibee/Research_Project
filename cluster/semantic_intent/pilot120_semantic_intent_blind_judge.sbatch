#!/usr/bin/env bash
# Prediction-blind judge job.  The submit directory must contain only the
# blind bundle plus this runner/lifecycle script: never SEALED mapping/results.
#SBATCH --job-name=p120-semjudge
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --nodelist=mscluster110
#SBATCH --time=24:00:00
#SBATCH --output=%x-%j.out
#SBATCH --error=%x-%j.err
set -Eeuo pipefail

: "${JUDGE_ID:?set Judge_A or Judge_B}"
: "${JUDGE_MODEL:?set local model path}"
: "${JUDGE_REVISION:?set pinned revision}"
: "${A01_CONTAINER_SIF:?set vLLM container path}"
[[ "$JUDGE_ID" == "Judge_A" || "$JUDGE_ID" == "Judge_B" ]] || { echo "invalid_judge_id" >&2; exit 2; }
JUDGE_PASSES="${JUDGE_PASSES:-1 2}"
[[ "$JUDGE_PASSES" =~ ^[12](\ [12])?$ ]] || { echo "invalid_judge_passes:$JUDGE_PASSES" >&2; exit 2; }
ROOT="${SLURM_SUBMIT_DIR:?}"
OUT="$ROOT/outputs/${JUDGE_ID}_${SLURM_JOB_ID}"
mkdir -p "$OUT"
exec > >(tee "$OUT/job.stdout.log") 2> >(tee "$OUT/job.stderr.log" >&2)

export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export A01_MAX_MODEL_LEN=8192 A02_READY_TIMEOUT_SECONDS=900
command -v nvidia-smi >/dev/null
GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
GPU_MEM="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)"
[[ "$GPU_NAME" == *Blackwell* ]] || { echo "incompatible_gpu:${GPU_NAME}" >&2; exit 42; }
[[ "${GPU_MEM:-0}" -ge 90000 ]] || { echo "insufficient_gpu_memory_mib:${GPU_MEM}" >&2; exit 42; }
GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)"
[[ "${GPU_USED:-999999}" -le 1000 ]] || { echo "gpu_not_idle:${GPU_USED}" >&2; exit 42; }

for PASS in $JUDGE_PASSES; do
  # Each lifecycle invocation launches and tears down the model: a fresh context.
  PORT=$((8100 + PASS))
  python3 scripts/semantic_intent/server_lifecycle.py \
    --model "$JUDGE_MODEL" --revision "$JUDGE_REVISION" --port "$PORT" \
    --runner scripts/semantic_intent/run_blind_semantic_judge.py \
    --log "$OUT/${JUDGE_ID}_pass_${PASS}.server.log" --runner-args \
      --packet "blind_bundle/data/blind_judge_pass_${PASS}_120.jsonl" \
      --guide blind_bundle/protocol/JUDGE_GUIDE.md \
      --prompt blind_bundle/protocol/JUDGE_PROMPT.txt \
      --schema blind_bundle/protocol/judge_output_schema.json \
      --calibration blind_bundle/protocol/synthetic_judge_calibration.jsonl \
      --judge-id "$JUDGE_ID" --model "$JUDGE_MODEL" --revision "$JUDGE_REVISION" \
      --port "$PORT" --out "$OUT/${JUDGE_ID}_pass_${PASS}.jsonl" \
      --manifest-out "$OUT/${JUDGE_ID}_pass_${PASS}.manifest.json" \
      --seed "$((20260902 + PASS))"
done
sha256sum "$OUT/${JUDGE_ID}_pass_1.jsonl" "$OUT/${JUDGE_ID}_pass_2.jsonl" > "$OUT/SHA256SUMS"
