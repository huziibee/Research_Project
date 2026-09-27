#!/usr/bin/env bash
# From a machine that can SSH to wits-mscluster: rsync code + gold, then submit.
set -euo pipefail
REMOTE="${REMOTE:-wits-mscluster}"
DEST="${DEST:-/home-mscluster/mbangie/t12-hpc/code/qwen_natives-20260914}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

ssh -o BatchMode=yes -o ConnectTimeout=25 "${REMOTE}" "mkdir -p '${DEST}' /home-mscluster/mbangie/t12-hpc/results/qwen_natives-20260914 /home-mscluster/mbangie/t12-hpc/results/official_sidecar_scores-20260914 /home-mscluster/mbangie/t12-hpc/logs"

rsync -a --delete \
  --exclude '.git/' \
  --exclude 'outputs/' \
  --exclude 'review_bundles/' \
  --exclude 'pilot120_historical_annotation_handoff/' \
  --exclude '.t41_closure_work/' \
  --exclude '__pycache__/' \
  "${ROOT}/scripts/" "${REMOTE}:${DEST}/scripts/"
rsync -a --delete "${ROOT}/cluster/qwen_natives_20260914/" "${REMOTE}:${DEST}/cluster/qwen_natives_20260914/"
rsync -a --delete "${ROOT}/src/ambiguity_manager/" "${REMOTE}:${DEST}/src/ambiguity_manager/"
rsync -a "${ROOT}/configs/evaluation/pilot_120_v1.json" "${REMOTE}:${DEST}/configs/evaluation/"
rsync -a \
  "${ROOT}/data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl" \
  "${ROOT}/data/annotations/pilot_120_v1/pilot_120_final_gold_with_cpc.jsonl" \
  "${ROOT}/data/annotations/pilot_120_v1/pilot_120_gold_cpc_official.jsonl" \
  "${ROOT}/data/annotations/pilot_120_v1/pilot_120_gold_risk_official.jsonl" \
  "${REMOTE}:${DEST}/data/annotations/pilot_120_v1/"
rsync -a "${ROOT}/pilot120_t41_complete_closure/final_t41/pilot120_interpretation_gold_final.jsonl" \
  "${REMOTE}:${DEST}/pilot120_t41_complete_closure/final_t41/"
ssh -o BatchMode=yes "${REMOTE}" "chmod +x '${DEST}/cluster/qwen_natives_20260914/'*.sh '${DEST}/cluster/qwen_natives_20260914/'*.sbatch; sed -i 's/\r$//' '${DEST}/cluster/qwen_natives_20260914/'*.sh '${DEST}/cluster/qwen_natives_20260914/'*.sbatch; QWEN_NATIVE_CODE_ROOT='${DEST}' bash '${DEST}/cluster/qwen_natives_20260914/submit.sh'"
