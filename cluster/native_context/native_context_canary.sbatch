#!/usr/bin/env bash
# Target-free structured canary for CLARA/Indirect; no frozen Pilot inputs.
#SBATCH --job-name=native-context
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=04:00:00
set -Eeuo pipefail
: "${TASKS:?set one or more of clara indirect}"; : "${SYSTEM:?}"; : "${A01_CONTAINER_SIF:?}"; ROOT="$SLURM_SUBMIT_DIR"; OUT="$ROOT/outputs/${SYSTEM}_${SLURM_JOB_ID}";mkdir -p "$OUT";exec > >(tee "$OUT/job.stdout.log") 2> >(tee "$OUT/job.stderr.log" >&2)
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 A01_MAX_MODEL_LEN=8192 A02_READY_TIMEOUT_SECONDS=900
[[ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits|head -1)" -le 1000 ]]||exit 42
if [[ "$SYSTEM" == gemma4 ]];then M=/home-mscluster/mbangie/models/dual_llm_benchmark_v1/gemma-4-26b-a4b-it;R=4d7ae4984b7db7de8f8457170b3f1a419ee76d52;P=8401;else M=/home-mscluster/mbangie/models/dual_llm_benchmark_v1/glm-4.7-flash-bf16;R=7dd20894a642a0aa287e9827cb1a1f7f91386b67;P=8402;fi
LIMIT="${RUN_LIMIT:-4}"
for TASK in $TASKS; do
LIMIT_ARGS=(); [[ "$LIMIT" == all ]] || LIMIT_ARGS=(--limit "$LIMIT")
python3 scripts/annotation/server_lifecycle.py --model "$M" --revision "$R" --port "$P" --runner scripts/run_native_context_structured.py --log "$OUT/${TASK}.server.log" --runner-args --task "$TASK" --packet "inputs/${TASK}.jsonl" --prompt "protocol/${TASK}.txt" --model "$M" --revision "$R" --port "$P" --out "$OUT/${TASK}.predictions.jsonl" --manifest-out "$OUT/${TASK}.manifest.json" --seed 20260908 "${LIMIT_ARGS[@]}"
EXPECTED="$LIMIT"; [[ "$LIMIT" == all ]] && EXPECTED=$([[ "$TASK" == clara ]] && echo 10444 || echo 906)
[[ "$(wc -l < "$OUT/${TASK}.predictions.jsonl")" == "$EXPECTED" ]]||exit 42
done
