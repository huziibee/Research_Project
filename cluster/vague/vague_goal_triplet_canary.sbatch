#!/usr/bin/env bash
# Target-free VAGUE goal-triplet canary. This is not a T39/T41 rerun.
#SBATCH --job-name=vague-goal-canary
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --nodelist=mscluster110
#SBATCH --time=04:00:00
#SBATCH --output=%x-%j.out
#SBATCH --error=%x-%j.err
set -Eeuo pipefail

: "${VAGUE_SYSTEM:?set gemma4 or glm47}"
: "${A01_CONTAINER_SIF:?set pinned vLLM container}"
[[ "$VAGUE_SYSTEM" == gemma4 || "$VAGUE_SYSTEM" == glm47 ]] || { echo "invalid_vague_system" >&2; exit 2; }
ROOT="${SLURM_SUBMIT_DIR:?}"; OUT="$ROOT/outputs/${VAGUE_SYSTEM}_${SLURM_JOB_ID}"; mkdir -p "$OUT"
exec > >(tee "$OUT/job.stdout.log") 2> >(tee "$OUT/job.stderr.log" >&2)
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export A01_MAX_MODEL_LEN=8192 A02_READY_TIMEOUT_SECONDS=900
GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"; GPU_MEM="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)"; GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)"
[[ "$GPU_NAME" == *Blackwell* && "${GPU_MEM:-0}" -ge 90000 && "${GPU_USED:-999999}" -le 1000 ]] || { echo "incompatible_or_busy_gpu:$GPU_NAME:$GPU_MEM:$GPU_USED" >&2; exit 42; }
if [[ "$VAGUE_SYSTEM" == gemma4 ]]; then MODEL=/home-mscluster/mbangie/models/dual_llm_benchmark_v1/gemma-4-26b-a4b-it; REVISION=4d7ae4984b7db7de8f8457170b3f1a419ee76d52; PORT=8201; else MODEL=/home-mscluster/mbangie/models/dual_llm_benchmark_v1/glm-4.7-flash-bf16; REVISION=7dd20894a642a0aa287e9827cb1a1f7f91386b67; PORT=8202; fi
LIMIT="${RUN_LIMIT:-4}"; LIMIT_ARGS=(); [[ "$LIMIT" == all ]] || LIMIT_ARGS=(--limit "$LIMIT")
python3 scripts/annotation/server_lifecycle.py --model "$MODEL" --revision "$REVISION" --port "$PORT" --runner scripts/run_vague_goal_triplet.py --log "$OUT/server.log" --runner-args --packet inputs/vague_inference_packet.jsonl --prompt protocol/vague_goal_triplet_prompt_v1.txt --model "$MODEL" --revision "$REVISION" --port "$PORT" --out "$OUT/predictions.jsonl" --manifest-out "$OUT/run_manifest.json" --seed 20260908 "${LIMIT_ARGS[@]}"
[[ "$(wc -l < "$OUT/predictions.jsonl")" == "$([[ "$LIMIT" == all ]] && echo 3354 || echo "$LIMIT")" ]] || { echo "output_count_invalid" >&2; exit 42; }
sha256sum "$OUT/predictions.jsonl" "$OUT/run_manifest.json" > "$OUT/SHA256SUMS"
echo "VAGUE_GOAL_TRIPLET_CANARY_PASS system=$VAGUE_SYSTEM records=4"
