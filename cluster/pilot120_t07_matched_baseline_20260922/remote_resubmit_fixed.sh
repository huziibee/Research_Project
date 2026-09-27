#!/usr/bin/env bash
set -euo pipefail
# Sync fixed sbatch scripts and resubmit recovery + T07 matched baseline.

OVERLAY=/tmp/p120_fix_resubmit
mkdir -p "$OVERLAY"

REC_CODE=/home-mscluster/mbangie/t12-hpc/code/pilot120_one_turn_recovery-20260922
T07_CODE=/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922
REC_OUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922
T07_OUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922

cp -f "$OVERLAY/one_turn_recovery.sbatch" \
  "$REC_CODE/cluster/pilot120_one_turn_recovery_20260922/one_turn_recovery.sbatch"
cp -f "$OVERLAY/t07_matched_baseline.sbatch" \
  "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922/t07_matched_baseline.sbatch"
sed -i 's/\r$//' \
  "$REC_CODE/cluster/pilot120_one_turn_recovery_20260922/one_turn_recovery.sbatch" \
  "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922/t07_matched_baseline.sbatch"
chmod +x \
  "$REC_CODE/cluster/pilot120_one_turn_recovery_20260922/one_turn_recovery.sbatch" \
  "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922/t07_matched_baseline.sbatch"

# Confirm fixes present
grep -n 'mscluster111\|cuda_preflight\|PYTHONPATH=\${GFV2_TRAINING' \
  "$REC_CODE/cluster/pilot120_one_turn_recovery_20260922/one_turn_recovery.sbatch" | head
grep -n 'mscluster111\|using_official_adapter\|official_adapter_requires' \
  "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922/t07_matched_baseline.sbatch" | head

export REC_CODE_ROOT="$REC_CODE" REC_OUTPUT="$REC_OUT" \
  GFV2_CONTAINER=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif \
  GFV2_HF_HOME=/home-mscluster/mbangie/t12-hpc/hf-cache \
  GFV2_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-hpc/training-site-packages \
  AFTERANY=0
bash "$REC_CODE/cluster/pilot120_one_turn_recovery_20260922/submit.sh"
REC_JID=$(awk -F'\t' '/one_turn_recovery/{print $2; exit}' "$REC_OUT/submission.tsv")
echo "recovery_jid=${REC_JID}"

export T07_CODE_ROOT="$T07_CODE" T07_OUTPUT="$T07_OUT" \
  A01_CONTAINER_SIF=/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif \
  AFTERANY="${REC_JID}" \
  T07_GF_PREDS="$T07_CODE/artifacts_t07/goal_first_manager_v2.predictions.jsonl" \
  T07_BLIND_PREDS="$T07_CODE/artifacts_t07/goal_first_context_blind_v2.predictions.jsonl" \
  T07_DEGREE_PREDS="$T07_CODE/artifacts_t07/degree_based_router_v2.predictions.jsonl" \
  T07_TIMID_PREDS="$T07_CODE/artifacts_t07/rich_conservative_manager_v2.predictions.jsonl"
bash "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922/submit.sh"
squeue -u mbangie
