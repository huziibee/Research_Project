#!/usr/bin/env bash
# Submit capability-judge + debate pack after unified job (default afterany:55670).
set -euo pipefail
umask 077

: "${CAP_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/pilot120_capability_debate-20260918}"
: "${CAP_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/pilot120_capability_debate-20260918}"
: "${CAP_PREDICTIONS:=/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915/T0.7/predictions/goal_first_manager_v2.predictions.jsonl}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"
: "${AFTERANY:=55670}"

HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "${CAP_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs
export CAP_CODE_ROOT CAP_OUTPUT CAP_PREDICTIONS GFV2_CONTAINER GFV2_HF_HOME GFV2_TRAINING_SITE_PACKAGES

EXTRA=()
if [[ -n "${AFTERANY}" && "${AFTERANY}" != "0" && "${AFTERANY}" != "none" ]]; then
  EXTRA+=(--dependency="afterany:${AFTERANY}")
fi

jid=$(sbatch --parsable "${EXTRA[@]}" --export=ALL "${HERE}/capability_debate.sbatch")
echo "submitted_capability_debate ${jid} afterany=${AFTERANY}"
printf 'capability_debate\t%s\tafterany\t%s\tout\t%s\npred\t%s\n' \
  "${jid}" "${AFTERANY}" "${CAP_OUTPUT}" "${CAP_PREDICTIONS}" \
  | tee "${CAP_OUTPUT}/submission.tsv"
squeue -u mbangie
