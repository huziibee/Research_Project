#!/usr/bin/env bash
# Run from WSL. Syncs Windows checkout to cluster and submits the GPU job.
set -euo pipefail

WIN_ROOT="/mnt/c/Users/huzii/Documents/University/Research Project"
REMOTE="${REMOTE:-wits-mscluster}"
DEST="${DEST:-/home-mscluster/mbangie/t12-hpc/code/pilot120_one_turn_recovery-20260922}"
OUT="${OUT:-/home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922}"

test -d "${WIN_ROOT}/src"
test -f "${WIN_ROOT}/scripts/one_turn_recovery_20260922.py"
test -f "${WIN_ROOT}/outputs/one_turn_recovery_20260922/01_frozen_manifest.json"

# Ensure SSH host alias
mkdir -p ~/.ssh
chmod 700 ~/.ssh
if ! grep -q "Host wits-mscluster" ~/.ssh/config 2>/dev/null; then
  cat >> ~/.ssh/config <<'EOF'
Host wits-mscluster
    HostName 146.141.21.100
    User mbangie
    IdentityFile /mnt/c/Users/huzii/.ssh/id_ed25519_wits
    IdentitiesOnly yes
EOF
fi
chmod 600 ~/.ssh/config

ssh -o BatchMode=yes -o ConnectTimeout=30 "${REMOTE}" \
  "mkdir -p '${DEST}' '${DEST}/cluster/pilot120_one_turn_recovery_20260922' \
   '${DEST}/evidence_pack_A/03_gold_and_metrics' \
   '${DEST}/evidence_pack_A/08_predictions_and_emits/unified_55670_repaired_20260918/T0.7/predictions' \
   '${DEST}/evidence_pack_A/08_predictions_and_emits/clarify_cpc_rescue_20260918' \
   '${DEST}/evidence_pack_A/08_predictions_and_emits/capability_debate_local_oracle_20260918' \
   '${OUT}/one_turn_recovery_20260922' /home-mscluster/mbangie/t12-hpc/logs"

rsync -az --delete \
  --exclude '.git' --exclude 'outputs' --exclude 'latest results' --exclude 'results' \
  --exclude 'review_packs' --exclude 'review_bundles' --exclude '.t41_closure_work' \
  --exclude 'pilot120_t41_complete_closure' --exclude 'cluster/mega_close_20260913' \
  "${WIN_ROOT}/src" "${WIN_ROOT}/scripts" "${WIN_ROOT}/data" "${WIN_ROOT}/configs" \
  "${REMOTE}:${DEST}/"

rsync -az "${WIN_ROOT}/cluster/pilot120_one_turn_recovery_20260922/" \
  --exclude '_wsl_*' \
  "${REMOTE}:${DEST}/cluster/pilot120_one_turn_recovery_20260922/"

PACK="${WIN_ROOT}/outputs/paper_writer_handoff_20260922/A_EVIDENCE_FOR_PAPER"
rsync -az \
  "${PACK}/03_gold_and_metrics/pilot120_joined_ground_truth.jsonl" \
  "${REMOTE}:${DEST}/evidence_pack_A/03_gold_and_metrics/"
rsync -az \
  "${PACK}/08_predictions_and_emits/unified_55670_repaired_20260918/T0.7/predictions/goal_first_manager_v2.predictions.jsonl" \
  "${REMOTE}:${DEST}/evidence_pack_A/08_predictions_and_emits/unified_55670_repaired_20260918/T0.7/predictions/"
rsync -az \
  "${PACK}/08_predictions_and_emits/clarify_cpc_rescue_20260918/goal_first_v2.llmcap_route_scene_clarify.predictions.jsonl" \
  "${REMOTE}:${DEST}/evidence_pack_A/08_predictions_and_emits/clarify_cpc_rescue_20260918/"
rsync -az \
  "${PACK}/08_predictions_and_emits/capability_debate_local_oracle_20260918/capability_judgments_cluster.jsonl" \
  "${REMOTE}:${DEST}/evidence_pack_A/08_predictions_and_emits/capability_debate_local_oracle_20260918/"

rsync -az "${WIN_ROOT}/outputs/one_turn_recovery_20260922/" \
  "${REMOTE}:${OUT}/one_turn_recovery_20260922/"

ssh -o BatchMode=yes "${REMOTE}" \
  "chmod +x '${DEST}/cluster/pilot120_one_turn_recovery_20260922/'*.sh \
             '${DEST}/cluster/pilot120_one_turn_recovery_20260922/'*.sbatch; \
   sed -i 's/\r$//' '${DEST}/cluster/pilot120_one_turn_recovery_20260922/'*.sh \
                    '${DEST}/cluster/pilot120_one_turn_recovery_20260922/'*.sbatch \
                    '${DEST}/scripts/one_turn_recovery_20260922.py'; \
   export REC_CODE_ROOT='${DEST}' \
          REC_OUTPUT='${OUT}' \
          GFV2_CONTAINER=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif \
          GFV2_HF_HOME=/home-mscluster/mbangie/t12-hpc/hf-cache \
          GFV2_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-hpc/training-site-packages \
          AFTERANY=0; \
   bash '${DEST}/cluster/pilot120_one_turn_recovery_20260922/submit.sh'"
