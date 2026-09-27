#!/usr/bin/env bash
# Submit the three-task native retry. Call only when 53188 no longer holds the GPU
# (or with --dependency afterok/afterany). Does not overwrite complete natives.
set -euo pipefail
umask 077

export GFV2_CODE_ROOT=/home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911
export FOLLOWON_NATIVE_ROOT=/home-mscluster/mbangie/t12-hpc/code/followon-native-20260911
export FOLLOWON_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b
export A01_CONTAINER_SIF=/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif
export A01_MAX_MODEL_LEN="${A01_MAX_MODEL_LEN:-8192}"
export A02_READY_TIMEOUT_SECONDS="${A02_READY_TIMEOUT_SECONDS:-900}"

DEP="${1:-}"
extra=()
if [[ -n "${DEP}" ]]; then
  extra+=(--dependency="${DEP}")
fi

JOB_ID=$(sbatch --parsable --export=ALL "${extra[@]}" \
  "${FOLLOWON_NATIVE_ROOT}/cluster/followon_53074/retry_missing_natives.sbatch")
echo "native_retry=${JOB_ID}"
squeue -j "${JOB_ID}" || true
