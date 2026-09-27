#!/usr/bin/env bash
# Queue the 3-day follow-on behind replica-1 job 53074.
set -euo pipefail
umask 077

: "${GFV2_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${GFV2_SELECTED_ADAPTER:=/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/early_pilot_package_excluding_clara1170_v1}"
: "${GFV2_ADAPTER_IDENTITY:=${GFV2_SELECTED_ADAPTER}/adapter_identity.json}"
: "${GFV2_ADAPTER_SCALE:=0.18}"
: "${A01_CONTAINER_SIF:=/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif}"
: "${FOLLOWON_NATIVE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/followon-native-20260911}"
: "${FOLLOWON_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260911}"
: "${FOLLOWON_AFTER:=53074}"

if [[ -e "${FOLLOWON_OUTPUT}" ]]; then
  echo "followon_output_must_be_new:${FOLLOWON_OUTPUT}" >&2
  exit 2
fi
mkdir -p "${FOLLOWON_OUTPUT}" "$(dirname "${FOLLOWON_OUTPUT}")" "${FOLLOWON_NATIVE_ROOT}"

export GFV2_CODE_ROOT GFV2_TRAINING_SITE_PACKAGES GFV2_HF_HOME GFV2_CONTAINER
export GFV2_SELECTED_ADAPTER GFV2_ADAPTER_IDENTITY GFV2_ADAPTER_SCALE
export A01_CONTAINER_SIF FOLLOWON_NATIVE_ROOT FOLLOWON_OUTPUT

job_id=$(sbatch --parsable --dependency="afterok:${FOLLOWON_AFTER}" --export=ALL \
  "${FOLLOWON_NATIVE_ROOT}/cluster/followon_53074/combined.sbatch")
printf 'job_id\t%s\nafter\t%s\noutput\t%s\n' "${job_id}" "${FOLLOWON_AFTER}" "${FOLLOWON_OUTPUT}" \
  | tee "${FOLLOWON_OUTPUT}/submission.tsv"
echo "submitted ${job_id} afterok:${FOLLOWON_AFTER}"
