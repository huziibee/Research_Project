#!/usr/bin/env bash
set -euo pipefail

EXP=/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922/t07_matched_baseline_completion_20260922
T07=/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922

echo "=== SQUEUE ==="
squeue -u mbangie
echo "=== 58561 ==="
sacct -j 58561 --format=JobID,JobName,State,Elapsed,ExitCode,NodeList -P

echo "=== INTEGRITY ==="
python3 - <<'PY'
import json
from pathlib import Path
exp = Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922/t07_matched_baseline_completion_20260922")
ids = [l.strip() for l in (exp/"02_input_case_ids.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
assert len(ids)==120 and len(set(ids))==120
for name in ("06_raw_qwen_t07.predictions.jsonl","07_finetune_t07.predictions.jsonl"):
    rows=[json.loads(l) for l in (exp/name).read_text(encoding="utf-8").splitlines() if l.strip()]
    rids=[r["record_id"] for r in rows]
    failed=sum(1 for r in rows if r.get("failed"))
    print(name, "n", len(rows), "unique", len(set(rids)), "order_ok", rids==ids, "failed", failed)
print("judges_dir", (exp/"judges").exists())
print("box_sgc", (exp/"judges/intent_box_raw_ft/final/sgc_rows.jsonl").exists())
print("mgr_sgc", (exp/"judges/gfv2_intent_summary_t07/final/sgc_rows.jsonl").exists())
print("packets", (exp/"packets/intent_box_sgc_t07/blind_judge_pass_1_120.jsonl").exists())
PY

# Cancel ABLE IX / T0.3 chain so T0.7 judging is the only GPU job.
squeue -u mbangie -h -o '%i %j' | awk '/p120-able/{print $1}' | while read -r jid; do
  scancel "${jid}" || true
  echo "cancelled_able ${jid}"
done

# Install updated scoring/packaging that 58561 will call at the end.
cp -f /tmp/score_t07_matched_baseline_20260922.py "${T07}/scripts/score_t07_matched_baseline_20260922.py"
cp -f /tmp/finalize_t07_paper_pack_20260923.py "${T07}/scripts/finalize_t07_paper_pack_20260923.py"
cp -f /tmp/20_ADAPTER_PROVENANCE_NOTE.md "${EXP}/20_ADAPTER_PROVENANCE_NOTE.md"
test -f "${T07}/scripts/score_t07_matched_baseline_20260922.py"
test -f "${T07}/scripts/finalize_t07_paper_pack_20260923.py"

# Keep 58561 if still pending/running. If it vanished, resubmit one judge+score job.
STATE="$(sacct -j 58561 --format=State --noheader -X | awk '{print $1}' | head -1 || true)"
echo "58561_state=${STATE}"
if [[ "${STATE}" != "PENDING" && "${STATE}" != "RUNNING" && "${STATE}" != "CONFIGURING" ]]; then
  echo "resubmitting_t07_judge_job"
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
  bash "${T07}/cluster/pilot120_t07_matched_baseline_20260922/submit.sh"
fi

squeue -u mbangie
echo PRIORITY_T07_READY
