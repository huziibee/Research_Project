#!/usr/bin/env bash
set -euo pipefail

FC=/home-mscluster/mbangie/t12-hpc/code/final_close-20260913
T07_CODE=/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922
T07_OUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922

# Ensure overlay extracted
if [[ ! -d /tmp/p120_overlay_extract/scripts ]]; then
  mkdir -p /tmp/p120_overlay_extract
  tar -xzf /tmp/p120_t07_overlay.tar.gz -C /tmp/p120_overlay_extract
fi

# Recovery multi-depth patch (idempotent)
REC_CODE=/home-mscluster/mbangie/t12-hpc/code/pilot120_one_turn_recovery-20260922
cp -f /tmp/p120_overlay_extract/scripts/one_turn_recovery_20260922.py "$REC_CODE/scripts/"
cp -f /tmp/p120_overlay_extract/cluster/pilot120_one_turn_recovery_20260922/one_turn_recovery.sbatch \
  "$REC_CODE/cluster/pilot120_one_turn_recovery_20260922/"
sed -i 's/\r$//' "$REC_CODE/scripts/one_turn_recovery_20260922.py" \
  "$REC_CODE/cluster/pilot120_one_turn_recovery_20260922/"*.sbatch || true
echo "recovery_patched"

# Fast T07 layout: symlink shared trees from final_close
rm -rf "$T07_CODE"
mkdir -p "$T07_CODE/scripts" "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922" \
  "$T07_CODE/artifacts_t07" "$T07_OUT/t07_matched_baseline_completion_20260922"
ln -sfn "$FC/src" "$T07_CODE/src"
ln -sfn "$FC/data" "$T07_CODE/data"
ln -sfn "$FC/configs" "$T07_CODE/configs"
ln -sfn "$FC/pilot120_intent_evaluation_20260902" "$T07_CODE/pilot120_intent_evaluation_20260902"
# Copy scripts tree then overlay new ones (cannot mix symlink dir + file easily)
rsync -a "$FC/scripts/" "$T07_CODE/scripts/"
cp -f /tmp/p120_overlay_extract/scripts/build_t07_manager_sgc_packet_20260922.py "$T07_CODE/scripts/"
cp -f /tmp/p120_overlay_extract/scripts/score_t07_matched_baseline_20260922.py "$T07_CODE/scripts/"
cp -f /tmp/p120_overlay_extract/cluster/pilot120_t07_matched_baseline_20260922/* \
  "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922/"
cp -f /tmp/p120_overlay_extract/artifacts_t07/* "$T07_CODE/artifacts_t07/"
rsync -a /tmp/p120_overlay_extract/outputs/t07_matched_baseline_completion_20260922/ \
  "$T07_OUT/t07_matched_baseline_completion_20260922/"
sed -i 's/\r$//' "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922/"*.sh \
  "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922/"*.sbatch \
  "$T07_CODE/scripts/build_t07_manager_sgc_packet_20260922.py" \
  "$T07_CODE/scripts/score_t07_matched_baseline_20260922.py"
chmod +x "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922/"*.sh \
  "$T07_CODE/cluster/pilot120_t07_matched_baseline_20260922/"*.sbatch
test -f "$T07_CODE/scripts/evaluate_pilot_120_intent_box.py"
test -f "$T07_CODE/scripts/annotation/server_lifecycle.py"
test -f "$T07_OUT/t07_matched_baseline_completion_20260922/01_manifest.json"
wc -l "$T07_CODE/artifacts_t07/"*.jsonl
echo "t07_code_ready"

# Avoid duplicate pending T07 jobs
if squeue -u mbangie -n p120-t07-match -h | grep -q .; then
  echo "t07_job_already_queued"
  squeue -u mbangie
  exit 0
fi

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
