#!/usr/bin/env bash
set -euo pipefail
umask 077
: "${CLOSE_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/final_close-20260913}"
: "${CLOSE_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/final_close-20260913}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${A01_CONTAINER_SIF:=/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif}"
: "${GFV2_SELECTED_ADAPTER:=/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/early_pilot_package_excluding_clara1170_v1}"
: "${GFV2_ADAPTER_IDENTITY:=${GFV2_SELECTED_ADAPTER}/adapter_identity.json}"
: "${GFV2_ADAPTER_SCALE:=0.18}"
mkdir -p "${CLOSE_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs
export CLOSE_CODE_ROOT CLOSE_OUTPUT
export GFV2_TRAINING_SITE_PACKAGES GFV2_HF_HOME GFV2_CONTAINER A01_CONTAINER_SIF
export GFV2_SELECTED_ADAPTER GFV2_ADAPTER_IDENTITY GFV2_ADAPTER_SCALE

SBATCH_ARGS=(--parsable --export=ALL)
if [[ -n "${CLOSE_AFTER_JOB:-}" ]]; then
  SBATCH_ARGS+=(--dependency=afterany:"${CLOSE_AFTER_JOB}")
fi
job_id=$(sbatch "${SBATCH_ARGS[@]}" \
  "${CLOSE_CODE_ROOT}/cluster/final_close_20260913/close.sbatch")
printf 'job_id\t%s\nafter\t%s\noutput\t%s\ncode\t%s\n' "${job_id}" "${CLOSE_AFTER_JOB:-none}" "${CLOSE_OUTPUT}" "${CLOSE_CODE_ROOT}" \
  | tee "${CLOSE_OUTPUT}/submission.tsv"
echo "submitted ${job_id} after:${CLOSE_AFTER_JOB:-none}"
