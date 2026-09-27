#!/usr/bin/env bash
# Re-emit Pilot-120 goal-first family with clarification generator 1.1.0 + CPC status repair,
# then CPU-score official wording + CPC sidecars.
# Submit behind mega-official (default 54259) when that job still holds biggpu.
set -euo pipefail
umask 077

: "${FIX_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/pilot120_fix_emit-20260915}"
: "${FIX_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/pilot120_fix_emit-20260915}"
: "${MEGA_JOB:=54259}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"
: "${GFV2_SELECTED_ADAPTER:=/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/early_pilot_package_excluding_clara1170_v1}"

mkdir -p "${FIX_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs
export FIX_CODE_ROOT FIX_OUTPUT
export GFV2_CONTAINER GFV2_HF_HOME GFV2_TRAINING_SITE_PACKAGES GFV2_SELECTED_ADAPTER

gpu_args=(--parsable --export=ALL)
if squeue -j "${MEGA_JOB}" -h >/dev/null 2>&1 && [[ -n "$(squeue -j "${MEGA_JOB}" -h)" ]]; then
  gpu_args+=(--dependency=afterany:"${MEGA_JOB}")
  echo "gpu_waits_for ${MEGA_JOB}"
else
  echo "mega_${MEGA_JOB}_not_in_queue_submit_gpu_now"
fi

gpu_id=$(sbatch "${gpu_args[@]}" \
  "${FIX_CODE_ROOT}/cluster/pilot120_fix_emit_20260915/fix_emit.sbatch")
echo "submitted fix-emit ${gpu_id}"

printf 'gpu_job\t%s\nafter\t%s\nout\t%s\n' \
  "${gpu_id}" "${MEGA_JOB}" "${FIX_OUTPUT}" \
  | tee "${FIX_OUTPUT}/submission.tsv"
