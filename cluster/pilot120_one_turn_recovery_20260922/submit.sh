#!/usr/bin/env bash
# Submit one-turn recovery GPU job (no dependency by default).
set -euo pipefail
umask 077

: "${REC_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/pilot120_one_turn_recovery-20260922}"
: "${REC_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"
: "${AFTERANY:=0}"

HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "${REC_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs
export REC_CODE_ROOT REC_OUTPUT GFV2_CONTAINER GFV2_HF_HOME GFV2_TRAINING_SITE_PACKAGES

EXTRA=()
if [[ -n "${AFTERANY}" && "${AFTERANY}" != "0" && "${AFTERANY}" != "none" ]]; then
  EXTRA+=(--dependency="afterany:${AFTERANY}")
fi

jid=$(sbatch --parsable "${EXTRA[@]}" --export=ALL "${HERE}/one_turn_recovery.sbatch")
echo "submitted_one_turn_recovery ${jid} afterany=${AFTERANY}"
printf 'one_turn_recovery\t%s\tafterany\t%s\tout\t%s\n' \
  "${jid}" "${AFTERANY}" "${REC_OUTPUT}" \
  | tee "${REC_OUTPUT}/submission.tsv"
squeue -u mbangie
