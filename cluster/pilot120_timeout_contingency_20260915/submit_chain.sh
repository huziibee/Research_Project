#!/usr/bin/env bash
# Chain: after MEGA_JOB → temp priority (0.7 → 1.0 → 0.3) → fix-emit.
set -euo pipefail
umask 077

: "${MEGA_JOB:=54259}"
: "${PRIO_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/pilot120_fix_emit-20260915}"
: "${PRIO_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915}"
: "${FIX_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/pilot120_fix_emit-20260915}"
: "${FIX_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/pilot120_fix_emit-20260915}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"

HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "${PRIO_OUTPUT}" "${FIX_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs

export PRIO_CODE_ROOT PRIO_OUTPUT FIX_CODE_ROOT FIX_OUTPUT
export GFV2_CONTAINER GFV2_HF_HOME GFV2_TRAINING_SITE_PACKAGES

# Cancel old fix-emit if it is only waiting on mega (we re-chain it after priority).
if squeue -j 54774 -h >/dev/null 2>&1 && [[ -n "$(squeue -j 54774 -h 2>/dev/null || true)" ]]; then
  echo "cancelling_old_fix_emit_54774_to_rechain"
  scancel 54774 || true
fi

prio_args=(--parsable --export=ALL)
if squeue -j "${MEGA_JOB}" -h >/dev/null 2>&1 && [[ -n "$(squeue -j "${MEGA_JOB}" -h 2>/dev/null || true)" ]]; then
  prio_args+=(--dependency=afterany:"${MEGA_JOB}")
  echo "temp_priority_waits_for ${MEGA_JOB}"
else
  echo "mega_${MEGA_JOB}_not_in_queue_submit_temp_priority_now"
fi

prio_id=$(sbatch "${prio_args[@]}" "${HERE}/temp_priority.sbatch")
echo "submitted_temp_priority ${prio_id}"

fix_id=$(sbatch --parsable --export=ALL --dependency=afterany:"${prio_id}" \
  "${FIX_CODE_ROOT}/cluster/pilot120_fix_emit_20260915/fix_emit.sbatch")
echo "submitted_fix_emit ${fix_id} after ${prio_id}"

printf 'mega\t%s\ntemp_priority\t%s\nfix_emit\t%s\nprio_out\t%s\nfix_out\t%s\n' \
  "${MEGA_JOB}" "${prio_id}" "${fix_id}" "${PRIO_OUTPUT}" "${FIX_OUTPUT}" \
  | tee "${PRIO_OUTPUT}/submission.tsv"
