#!/usr/bin/env bash
set -euo pipefail

mkdir -p /tmp/p120_overlay_extract
rm -rf /tmp/p120_overlay_extract/*
tar -xzf /tmp/p120_t07_overlay.tar.gz -C /tmp/p120_overlay_extract

# --- Update pending one-turn recovery script BEFORE job starts ---
REC_CODE=/home-mscluster/mbangie/t12-hpc/code/pilot120_one_turn_recovery-20260922
cp -f /tmp/p120_overlay_extract/scripts/one_turn_recovery_20260922.py "$REC_CODE/scripts/"
cp -f /tmp/p120_overlay_extract/cluster/pilot120_one_turn_recovery_20260922/one_turn_recovery.sbatch \
      "$REC_CODE/cluster/pilot120_one_turn_recovery_20260922/"
sed -i 's/\r$//' "$REC_CODE/scripts/one_turn_recovery_20260922.py" \
  "$REC_CODE/cluster/pilot120_one_turn_recovery_20260922/"*.sbatch \
  "$REC_CODE/cluster/pilot120_one_turn_recovery_20260922/"*.sh || true
grep -n "MAX_CLARIFY_DEPTH\|max-clarify-depth" "$REC_CODE/scripts/one_turn_recovery_20260922.py" | head
grep -n "max-clarify-depth" "$REC_CODE/cluster/pilot120_one_turn_recovery_20260922/one_turn_recovery.sbatch" | head
echo "recovery_script_updated_for_job_57984"

# --- Bootstrap T0.7 matched baseline from final_close code ---
T07_CODE=/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922
T07_OUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922
FC=/home-mscluster/mbangie/t12-hpc/code/final_close-20260913
mkdir -p "$T07_CODE" "$T07_OUT"
rsync -a --delete \
  --exclude '.git' --exclude 'outputs' --exclude 'results' \
  "$FC/src/" "$T07_CODE/src/"
rsync -a "$FC/scripts/" "$T07_CODE/scripts/"
rsync -a "$FC/data/" "$T07_CODE/data/"
rsync -a "$FC/configs/" "$T07_CODE/configs/"
rsync -a "$FC/pilot120_intent_evaluation_20260902/" "$T07_CODE/pilot120_intent_evaluation_20260902/"
mkdir -p "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922"
cp -f /tmp/p120_overlay_extract/cluster/pilot120_t07_matched_baseline_20260922/* \
  "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922/"
cp -f /tmp/p120_overlay_extract/scripts/build_t07_manager_sgc_packet_20260922.py "$T07_CODE/scripts/"
cp -f /tmp/p120_overlay_extract/scripts/score_t07_matched_baseline_20260922.py "$T07_CODE/scripts/"
test -f "$T07_CODE/scripts/evaluate_pilot_120_intent_box.py"
test -f "$T07_CODE/scripts/annotation/server_lifecycle.py"
mkdir -p "$T07_CODE/artifacts_t07"
cp -f /tmp/p120_overlay_extract/artifacts_t07/* "$T07_CODE/artifacts_t07/"
mkdir -p "$T07_OUT/t07_matched_baseline_completion_20260922"
rsync -a /tmp/p120_overlay_extract/outputs/t07_matched_baseline_completion_20260922/ \
  "$T07_OUT/t07_matched_baseline_completion_20260922/"
sed -i 's/\r$//' "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922/"*.sh \
  "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922/"*.sbatch \
  "$T07_CODE/scripts/build_t07_manager_sgc_packet_20260922.py" \
  "$T07_CODE/scripts/score_t07_matched_baseline_20260922.py"
chmod +x "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922/"*.sh \
  "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922/"*.sbatch
wc -l "$T07_CODE/artifacts_t07/"*.jsonl
test -f "$T07_OUT/t07_matched_baseline_completion_20260922/01_manifest.json"
echo "t07_code_ready"

export T07_CODE_ROOT="$T07_CODE" \
       T07_OUTPUT="$T07_OUT" \
       GFV2_CONTAINER=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif \
       GFV2_HF_HOME=/home-mscluster/mbangie/t12-hpc/hf-cache \
       GFV2_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-hpc/training-site-packages \
       A01_CONTAINER_SIF=/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif \
       AFTERANY=57984 \
       T07_GF_PREDS="$T07_CODE/artifacts_t07/goal_first_manager_v2.predictions.jsonl" \
       T07_BLIND_PREDS="$T07_CODE/artifacts_t07/goal_first_context_blind_v2.predictions.jsonl" \
       T07_DEGREE_PREDS="$T07_CODE/artifacts_t07/degree_based_router_v2.predictions.jsonl" \
       T07_TIMID_PREDS="$T07_CODE/artifacts_t07/rich_conservative_manager_v2.predictions.jsonl"
bash "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922/submit.sh"
