#!/usr/bin/env bash
set -euo pipefail
umask 077
: "${T07_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922}"
: "${T07_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${A01_CONTAINER_SIF:=/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif}"
: "${GFV2_SELECTED_ADAPTER:=/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/early_pilot_package_excluding_clara1170_v1}"
: "${GFV2_ADAPTER_IDENTITY:=${GFV2_SELECTED_ADAPTER}/adapter_identity.json}"
: "${GFV2_ADAPTER_SCALE:=0.18}"
: "${AFTERANY:=0}"

HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "${T07_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs
export T07_CODE_ROOT T07_OUTPUT GFV2_TRAINING_SITE_PACKAGES GFV2_HF_HOME GFV2_CONTAINER
export A01_CONTAINER_SIF GFV2_SELECTED_ADAPTER GFV2_ADAPTER_IDENTITY GFV2_ADAPTER_SCALE
export T07_GF_PREDS T07_BLIND_PREDS T07_DEGREE_PREDS T07_TIMID_PREDS

EXTRA=()
if [[ -n "${AFTERANY}" && "${AFTERANY}" != "0" && "${AFTERANY}" != "none" ]]; then
  EXTRA+=(--dependency="afterany:${AFTERANY}")
fi

jid=$(sbatch --parsable "${EXTRA[@]}" --export=ALL "${HERE}/t07_matched_baseline.sbatch")
echo "submitted_t07_matched_baseline ${jid} afterany=${AFTERANY}"
printf 't07_matched_baseline\t%s\tafterany\t%s\tout\t%s\n' \
  "${jid}" "${AFTERANY}" "${T07_OUTPUT}" | tee "${T07_OUTPUT}/submission.tsv"
squeue -u mbangie
