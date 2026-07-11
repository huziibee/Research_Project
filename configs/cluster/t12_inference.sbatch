#!/usr/bin/env bash
#SBATCH --job-name=t12-inference
#SBATCH --partition=biggpu
#SBATCH --exclusive
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=${T12_SLURM_CPUS:-8}
#SBATCH --mem=${T12_SLURM_MEM:-120000}
#SBATCH --time=${T12_SLURM_WALLTIME:-04:00:00}
#SBATCH --output=${T12_CLUSTER_ROOT}/logs/t12-inference-%j.out
#SBATCH --error=${T12_CLUSTER_ROOT}/logs/t12-inference-%j.err

set -euo pipefail

# Stage C2A template wiring. Persistent vLLM batch execution is invoked after preflight.
# Do not submit from local development without explicit human approval.

RUN_ID="${T12_RUN_ID:?T12_RUN_ID is required}"
SHARD_ID="${T12_SHARD_ID:?T12_SHARD_ID is required}"
CONFIG_PATH="${T12_CONFIG_PATH:?T12_CONFIG_PATH is required}"
RUNTIME_FACTS_PATH="${T12_RUNTIME_FACTS_PATH:?T12_RUNTIME_FACTS_PATH is required}"
PREFLIGHT_RESULT_PATH="${T12_PREFLIGHT_RESULT_PATH:?T12_PREFLIGHT_RESULT_PATH is required}"
SHARD_PLAN_PATH="${T12_SHARD_PLAN_PATH:?T12_SHARD_PLAN_PATH is required}"
RUN_DIR="${T12_RUN_DIR:?T12_RUN_DIR is required}"
VLLM_RUNTIME_CONFIG="${T12_VLLM_RUNTIME_CONFIG:?T12_VLLM_RUNTIME_CONFIG is required}"
INPUT_JSONL_PATH="${T12_INPUT_JSONL_PATH:?T12_INPUT_JSONL_PATH is required}"
SYNTHETIC_DECLARATION_PATH="${T12_SYNTHETIC_DECLARATION_PATH:?T12_SYNTHETIC_DECLARATION_PATH is required}"

NODE_LOCAL_TEMP="/var/tmp/${USER}-apptainer-${SLURM_JOB_ID}"
export NODE_LOCAL_TEMP
export HF_HOME="${T12_HF_CACHE}"
export HF_HUB_CACHE="${T12_HF_CACHE}/hub"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export T12_NETWORK_FALLBACK=false
export VLLM_WORKER_MULTIPROC_METHOD=spawn

cleanup() {
  if [[ -d "${NODE_LOCAL_TEMP}" ]]; then
    rm -rf "${NODE_LOCAL_TEMP}"
  fi
}
trap cleanup EXIT

mkdir -p "${NODE_LOCAL_TEMP}"

python scripts/t12_cluster_preflight.py \
  --runtime-facts "${RUNTIME_FACTS_PATH}" \
  --repo-root "${T12_REPO_ROOT:-.}" \
  --output "${PREFLIGHT_RESULT_PATH}"

python scripts/t12_cluster_run_batch.py \
  --runtime-config "${VLLM_RUNTIME_CONFIG}" \
  --shard-plan "${SHARD_PLAN_PATH}" \
  --shard-id "${SHARD_ID}" \
  --run-dir "${RUN_DIR}" \
  --preflight-result "${PREFLIGHT_RESULT_PATH}" \
  --input-jsonl "${INPUT_JSONL_PATH}" \
  --synthetic-declaration "${SYNTHETIC_DECLARATION_PATH}" \
  --repo-root "${T12_REPO_ROOT:-.}" \
  --start-timestamp "${T12_START_TIMESTAMP:?T12_START_TIMESTAMP is required}" \
  --end-timestamp "${T12_END_TIMESTAMP:?T12_END_TIMESTAMP is required}"

echo "Batch runner completed for run=${RUN_ID} shard=${SHARD_ID} config=${CONFIG_PATH}"
