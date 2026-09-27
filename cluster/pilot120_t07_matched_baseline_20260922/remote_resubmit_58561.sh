#!/usr/bin/env bash
set -euo pipefail
T07=/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922
cp -f /tmp/t07_matched_baseline.sbatch \
  "${T07}/cluster/pilot120_t07_matched_baseline_20260922/t07_matched_baseline.sbatch"
chmod +x "${T07}/cluster/pilot120_t07_matched_baseline_20260922/t07_matched_baseline.sbatch"

if squeue -u mbangie -h | grep -E 'p120-t07' >/dev/null; then
  echo "t07_already_queued"
  squeue -u mbangie
  exit 0
fi

export T07_CODE_ROOT="${T07}"
export T07_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922
export GFV2_CONTAINER=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif
export GFV2_HF_HOME=/home-mscluster/mbangie/t12-hpc/hf-cache
export GFV2_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-hpc/training-site-packages
export A01_CONTAINER_SIF=/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif
export AFTERANY=0
export T07_GF_PREDS="${T07}/artifacts_t07/goal_first_manager_v2.predictions.jsonl"
export T07_BLIND_PREDS="${T07}/artifacts_t07/goal_first_context_blind_v2.predictions.jsonl"
export T07_DEGREE_PREDS="${T07}/artifacts_t07/degree_based_router_v2.predictions.jsonl"
export T07_TIMID_PREDS="${T07}/artifacts_t07/rich_conservative_manager_v2.predictions.jsonl"
# Keep installed scorer/packager
test -f "${T07}/scripts/finalize_t07_paper_pack_20260923.py"
test -f "${T07}/scripts/score_t07_matched_baseline_20260922.py"
bash "${T07}/cluster/pilot120_t07_matched_baseline_20260922/submit.sh"
echo RESUBMIT_DONE
