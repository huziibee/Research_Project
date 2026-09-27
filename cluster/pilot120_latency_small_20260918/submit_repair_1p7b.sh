#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
: "${LAT_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/pilot120_latency_1p7b-20260918}"
: "${LAT_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/pilot120_latency_1p7b-20260918}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"
: "${LAT_MODEL:=Qwen/Qwen3-1.7B}"
: "${LAT_TEMPERATURE:=0.7}"

mkdir -p "${LAT_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs
EXTRA=()
[[ -n "${SLURM_ACCOUNT:-}" ]] && EXTRA+=(--account="${SLURM_ACCOUNT}")
jid=$(sbatch --parsable "${EXTRA[@]}" --export=ALL "${HERE}/repair_1p7b.sbatch")
echo "submitted:${jid}"
squeue -u mbangie
