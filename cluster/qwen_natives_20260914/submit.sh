#!/usr/bin/env bash
# Submit Qwen-native GPU job after mega-official, plus CPU sidecar scoring.
# bigbatch CPU can run while biggpu is busy; GPU waits for 54259.
set -euo pipefail
umask 077

: "${QWEN_NATIVE_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/qwen_natives-20260914}"
: "${QWEN_NATIVE_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/qwen_natives-20260914}"
: "${SIDECAR_SCORE_OUT:=/home-mscluster/mbangie/t12-hpc/results/official_sidecar_scores-20260914}"
: "${SWEEP_NATIVE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/temp_sweep-native-20260913}"
: "${CLOSE_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/final_close-20260913}"
: "${SWEEP_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/temp_sweep-20260913}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${GFV2_SELECTED_ADAPTER:=/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/early_pilot_package_excluding_clara1170_v1}"
: "${GFV2_ADAPTER_IDENTITY:=${GFV2_SELECTED_ADAPTER}/adapter_identity.json}"
: "${GFV2_ADAPTER_SCALE:=0.18}"
: "${MEGA_JOB:=54259}"

mkdir -p "${QWEN_NATIVE_OUTPUT}" "${SIDECAR_SCORE_OUT}" /home-mscluster/mbangie/t12-hpc/logs
export QWEN_NATIVE_CODE_ROOT QWEN_NATIVE_OUTPUT SIDECAR_SCORE_OUT SWEEP_NATIVE_ROOT
export CLOSE_OUTPUT SWEEP_OUTPUT
export GFV2_TRAINING_SITE_PACKAGES GFV2_HF_HOME GFV2_CONTAINER
export GFV2_SELECTED_ADAPTER GFV2_ADAPTER_IDENTITY GFV2_ADAPTER_SCALE

cpu_id=$(sbatch --parsable --export=ALL \
  "${QWEN_NATIVE_CODE_ROOT}/cluster/qwen_natives_20260914/sidecar_cpu_score.sbatch")
echo "submitted sidecar-cpu ${cpu_id}"

gpu_args=(--parsable --export=ALL)
if squeue -j "${MEGA_JOB}" -h >/dev/null 2>&1 && [[ -n "$(squeue -j "${MEGA_JOB}" -h)" ]]; then
  gpu_args+=(--dependency=afterany:"${MEGA_JOB}")
  echo "gpu_waits_for ${MEGA_JOB}"
else
  echo "mega_${MEGA_JOB}_not_in_queue_submit_gpu_now"
fi
gpu_id=$(sbatch "${gpu_args[@]}" \
  "${QWEN_NATIVE_CODE_ROOT}/cluster/qwen_natives_20260914/qwen_natives.sbatch")
echo "submitted qwen-natives ${gpu_id}"

printf 'cpu_job\t%s\ngpu_job\t%s\nafter\t%s\nnative_out\t%s\nscore_out\t%s\n' \
  "${cpu_id}" "${gpu_id}" "${MEGA_JOB}" "${QWEN_NATIVE_OUTPUT}" "${SIDECAR_SCORE_OUT}" \
  | tee "${QWEN_NATIVE_OUTPUT}/submission.tsv"
