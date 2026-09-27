#!/usr/bin/env bash
# Submit the 2026-09-13 generation temperature sweep (one array job).
# Reuses followon_53074 env defaults. Does not touch frozen trees.
set -euo pipefail
umask 077

: "${SWEEP_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/temp_sweep-20260913}"
: "${SWEEP_NATIVE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/temp_sweep-native-20260913}"
: "${SWEEP_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/temp_sweep-20260913}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${GFV2_SELECTED_ADAPTER:=/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/early_pilot_package_excluding_clara1170_v1}"
: "${GFV2_ADAPTER_IDENTITY:=${GFV2_SELECTED_ADAPTER}/adapter_identity.json}"
: "${GFV2_ADAPTER_SCALE:=0.18}"
: "${A01_CONTAINER_SIF:=/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif}"

case "${SWEEP_CODE_ROOT}${SWEEP_NATIVE_ROOT}${SWEEP_OUTPUT}" in
  *t39*|*t41*|*goal_first_v2-20260911*|*goal_first_followon-20260912b*)
    echo "refusing_frozen_path:${SWEEP_CODE_ROOT} ${SWEEP_NATIVE_ROOT} ${SWEEP_OUTPUT}" >&2
    exit 2
    ;;
esac

mkdir -p "${SWEEP_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs

export SWEEP_CODE_ROOT SWEEP_NATIVE_ROOT SWEEP_OUTPUT
export GFV2_TRAINING_SITE_PACKAGES GFV2_HF_HOME GFV2_CONTAINER
export GFV2_SELECTED_ADAPTER GFV2_ADAPTER_IDENTITY GFV2_ADAPTER_SCALE
export A01_CONTAINER_SIF

job_id=$(sbatch --parsable --export=ALL \
  "${SWEEP_CODE_ROOT}/cluster/temp_sweep_20260913/sweep.sbatch")
printf 'job_id\t%s\ngrid\t0-11_in_one_job\noutput\t%s\ncode\t%s\nnative\t%s\n' \
  "${job_id}" "${SWEEP_OUTPUT}" "${SWEEP_CODE_ROOT}" "${SWEEP_NATIVE_ROOT}" \
  | tee "${SWEEP_OUTPUT}/submission.tsv"
echo "submitted ${job_id}"
