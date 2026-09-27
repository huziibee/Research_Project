#!/usr/bin/env bash
# Sync local tree to dedicated cluster code root and submit capability/debate jobs.
set -euo pipefail
REMOTE="${REMOTE:-wits-mscluster}"
DEST="${DEST:-/home-mscluster/mbangie/t12-hpc/code/pilot120_capability_debate-20260918}"
AFTERANY="${AFTERANY:-55670}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PACK="$(cd "$(dirname "$0")" && pwd)"

ssh -o BatchMode=yes -o ConnectTimeout=30 "${REMOTE}" \
  "mkdir -p '${DEST}' \
    /home-mscluster/mbangie/t12-hpc/results/pilot120_capability_debate-20260918 \
    /home-mscluster/mbangie/t12-hpc/logs"

rsync -az \
  --exclude '.git' --exclude 'outputs' --exclude 'results/.obsidian' \
  --exclude 'node_modules' --exclude '__pycache__' \
  --exclude 'Pilot120_Results_Pack_*.zip' \
  "${ROOT}/" "${REMOTE}:${DEST}/"

ssh -o BatchMode=yes "${REMOTE}" \
  "chmod +x '${DEST}/cluster/pilot120_capability_debate_20260918/'*.sh; \
   sed -i 's/\r$//' '${DEST}/cluster/pilot120_capability_debate_20260918/'*.sh \
     '${DEST}/cluster/pilot120_capability_debate_20260918/'*.sbatch \
     '${DEST}/scripts/run_capability_llm_judge_20260918.py' \
     '${DEST}/scripts/reroute_patched_capability_20260918.py' \
     '${DEST}/scripts/run_ambiguity_debate_adjudicate_20260918.py' \
     '${DEST}/scripts/lib_capability_debate_20260918.py'; \
   # Prefer live T0.7 preds from unified output if present.
   PRED=/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915/T0.7/predictions/goal_first_manager_v2.predictions.jsonl; \
   if [[ ! -f \"\$PRED\" ]]; then echo missing_pred:\$PRED; exit 6; fi; \
   n=\$(wc -l < \"\$PRED\" | tr -d ' '); \
   echo pred_lines=\$n; \
   test \"\$n\" -ge 120 || exit 7; \
   CAP_CODE_ROOT='${DEST}' AFTERANY='${AFTERANY}' \
     bash '${DEST}/cluster/pilot120_capability_debate_20260918/submit.sh'"
