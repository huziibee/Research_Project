#!/usr/bin/env bash
# Repair incomplete code roots, then resubmit recovery + T0.7.
set -euo pipefail

FC=/home-mscluster/mbangie/t12-hpc/code/final_close-20260913
REC=/home-mscluster/mbangie/t12-hpc/code/pilot120_one_turn_recovery-20260922
T07=/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922
REC_OUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922
T07_OUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922

# --- Recovery: repo marker + freeze files used by router / optional eval ---
cp -f "$FC/pyproject.toml" "$REC/pyproject.toml"
if [[ ! -e "$REC/annotations" ]]; then
  ln -sfn "$FC/annotations" "$REC/annotations"
fi
test -f "$REC/pyproject.toml"
test -f "$REC/configs/annotation/route_precedence_v1.json"
test -f "$REC/src/ambiguity_manager/systems/routing.py"
test -f "$REC/scripts/one_turn_recovery_20260922.py"
echo "recovery_files_ok"

# --- T0.7: same freeze tree final_close already used for intent_box ---
cp -f "$FC/pyproject.toml" "$T07/pyproject.toml"
if [[ ! -e "$T07/annotations" ]]; then
  ln -sfn "$FC/annotations" "$T07/annotations"
fi
test -f "$T07/pyproject.toml"
test -f "$T07/annotations/manual_kappa_v7_final_protocol/subset_manifest.json"
test -f "$T07/scripts/evaluate_pilot_120_intent_box.py"
test -f "$T07/artifacts_t07/goal_first_manager_v2.predictions.jsonl"
echo "t07_files_ok"

# Preflight: router can resolve repo root; freeze hashes exist
python3 - <<'PY'
from pathlib import Path
import sys
rec = Path("/home-mscluster/mbangie/t12-hpc/code/pilot120_one_turn_recovery-20260922")
sys.path.insert(0, str(rec / "src"))
from ambiguity_manager.paths import repo_root
root = repo_root(rec / "src" / "ambiguity_manager" / "paths.py")
assert root == rec.resolve(), root
print("repo_root_ok", root)
PY

python3 - <<'PY'
from pathlib import Path
import sys
t07 = Path("/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922")
sys.path.insert(0, str(t07 / "src"))
sys.path.insert(0, str(t07 / "scripts"))
from evaluate_pilot_120_direct_base import verify_freeze
print(verify_freeze(t07))
PY

echo "preflight_ok"

# Do not double-queue if already pending/running
if squeue -u mbangie -h | grep -E 'p120-1tu|p120-t07' >/dev/null; then
  echo "jobs_already_queued"
  squeue -u mbangie
  exit 0
fi

export GFV2_CONTAINER=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif
export GFV2_HF_HOME=/home-mscluster/mbangie/t12-hpc/hf-cache
export GFV2_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-hpc/training-site-packages

export REC_CODE_ROOT="$REC" REC_OUTPUT="$REC_OUT" AFTERANY=0
bash "$REC/cluster/pilot120_one_turn_recovery_20260922/submit.sh"
REC_JID=$(awk -F'\t' '/one_turn_recovery/{print $2; exit}' "$REC_OUT/submission.tsv")
echo "recovery_jid=${REC_JID}"

export T07_CODE_ROOT="$T07" T07_OUTPUT="$T07_OUT" \
  A01_CONTAINER_SIF=/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif \
  AFTERANY="${REC_JID}" \
  T07_GF_PREDS="$T07/artifacts_t07/goal_first_manager_v2.predictions.jsonl" \
  T07_BLIND_PREDS="$T07/artifacts_t07/goal_first_context_blind_v2.predictions.jsonl" \
  T07_DEGREE_PREDS="$T07/artifacts_t07/degree_based_router_v2.predictions.jsonl" \
  T07_TIMID_PREDS="$T07/artifacts_t07/rich_conservative_manager_v2.predictions.jsonl"
bash "$T07/cluster/pilot120_t07_matched_baseline_20260922/submit.sh"
squeue -u mbangie
