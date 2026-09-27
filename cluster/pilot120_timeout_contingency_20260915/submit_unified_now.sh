#!/usr/bin/env bash
# Submit unified job now (mega stopped). No separate fix-emit needed.
set -euo pipefail
umask 077

: "${PRIO_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/pilot120_fix_emit-20260915}"
: "${PRIO_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"

HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "${PRIO_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs
export PRIO_CODE_ROOT PRIO_OUTPUT GFV2_CONTAINER GFV2_HF_HOME GFV2_TRAINING_SITE_PACKAGES

jid=$(sbatch --parsable --export=ALL "${HERE}/unified_fixed.sbatch")
echo "submitted_unified ${jid}"
printf 'unified\t%s\nout\t%s\norder\t0.5 0.7 1.0 then fix-reemit 0.0 0.3\n' \
  "${jid}" "${PRIO_OUTPUT}" | tee "${PRIO_OUTPUT}/unified_submission.tsv"
squeue -u mbangie
