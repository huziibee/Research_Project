#!/usr/bin/env bash
# Sync local tree to cluster and submit fix-emit behind mega (54259 by default).
set -euo pipefail
REMOTE="${REMOTE:-wits-mscluster}"
DEST="${DEST:-/home-mscluster/mbangie/t12-hpc/code/pilot120_fix_emit-20260915}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

ssh -o BatchMode=yes -o ConnectTimeout=25 "${REMOTE}" \
  "mkdir -p '${DEST}' /home-mscluster/mbangie/t12-hpc/results/pilot120_fix_emit-20260915 /home-mscluster/mbangie/t12-hpc/logs"

rsync -az --delete \
  --exclude '.git' --exclude 'outputs' --exclude 'results/.obsidian' \
  --exclude 'node_modules' --exclude '__pycache__' \
  "${ROOT}/" "${REMOTE}:${DEST}/"

ssh -o BatchMode=yes "${REMOTE}" \
  "chmod +x '${DEST}/cluster/pilot120_fix_emit_20260915/'*.sh; \
   sed -i 's/\r$//' '${DEST}/cluster/pilot120_fix_emit_20260915/'*.sh \
     '${DEST}/cluster/pilot120_fix_emit_20260915/'*.sbatch; \
   FIX_CODE_ROOT='${DEST}' bash '${DEST}/cluster/pilot120_fix_emit_20260915/submit.sh'"
