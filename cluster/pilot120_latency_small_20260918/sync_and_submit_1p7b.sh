#!/usr/bin/env bash
# Sync + submit Qwen3-1.7B Pilot-120 latency ablation @ T=0.7
set -euo pipefail
REMOTE="${REMOTE:-wits-mscluster}"
DEST="${DEST:-/home-mscluster/mbangie/t12-hpc/code/pilot120_latency_1p7b-20260918}"
OUT="${OUT:-/home-mscluster/mbangie/t12-hpc/results/pilot120_latency_1p7b-20260918}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

ssh -o BatchMode=yes -o ConnectTimeout=30 "${REMOTE}" \
  "mkdir -p '${DEST}' '${DEST}/cluster/pilot120_latency_small_20260918' \
   '${OUT}' /home-mscluster/mbangie/t12-hpc/logs"

rsync -az --delete \
  --exclude '.git' --exclude 'outputs' --exclude 'latest results' --exclude 'results' \
  --exclude 'review_packs' --exclude 'review_bundles' --exclude '.t41_closure_work' \
  --exclude 'pilot120_t41_complete_closure' --exclude 'cluster/mega_close_20260913' \
  "${ROOT}/src" "${ROOT}/scripts" "${ROOT}/data" "${ROOT}/configs" \
  "${REMOTE}:${DEST}/"

rsync -az "${ROOT}/cluster/pilot120_latency_small_20260918/" \
  "${REMOTE}:${DEST}/cluster/pilot120_latency_small_20260918/"

ssh -o BatchMode=yes "${REMOTE}" \
  "chmod +x '${DEST}/cluster/pilot120_latency_small_20260918/'*.sh \
             '${DEST}/cluster/pilot120_latency_small_20260918/'*.sbatch; \
   export LAT_CODE_ROOT='${DEST}' \
          LAT_OUTPUT='${OUT}' \
          GFV2_CONTAINER=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif \
          GFV2_HF_HOME=/home-mscluster/mbangie/t12-hpc/hf-cache \
          GFV2_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-hpc/training-site-packages \
          LAT_MODEL=Qwen/Qwen3-1.7B LAT_LIMIT=0 LAT_TEMPERATURE=0.7 \
          LAT_ALLOW_HF_DOWNLOAD=1 LAT_CONSTRAINED_ONLY=0; \
   bash '${DEST}/cluster/pilot120_latency_small_20260918/submit_1p7b.sh'"
