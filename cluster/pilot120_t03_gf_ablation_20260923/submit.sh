#!/usr/bin/env bash
set -euo pipefail
umask 077
: "${T03_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/pilot120_t03_gf_ablation-20260923}"
: "${T03_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/pilot120_t03_gf_ablation-20260923}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${AFTEROK:=0}"
: "${T03_SEEDS:=1 2 3}"

HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "${T03_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs
export T03_CODE_ROOT T03_OUTPUT GFV2_TRAINING_SITE_PACKAGES GFV2_HF_HOME GFV2_CONTAINER T03_SEEDS

EXTRA=()
if [[ -n "${AFTEROK}" && "${AFTEROK}" != "0" && "${AFTEROK}" != "none" ]]; then
  EXTRA+=(--dependency="afterok:${AFTEROK}")
fi

jid=$(sbatch --parsable "${EXTRA[@]}" --export=ALL "${HERE}/t03_gf_ablation.sbatch")
echo "submitted_t03_gf_ablation ${jid} afterok=${AFTEROK} seeds=${T03_SEEDS}"
printf 't03_gf_ablation\t%s\tafterok\t%s\tseeds\t%s\tout\t%s\n' \
  "${jid}" "${AFTEROK}" "${T03_SEEDS}" "${T03_OUTPUT}" | tee "${T03_OUTPUT}/submission.tsv"
squeue -u mbangie
