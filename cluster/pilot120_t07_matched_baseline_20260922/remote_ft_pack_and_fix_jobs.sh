#!/usr/bin/env bash
set -euo pipefail

EXP=/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922/t07_matched_baseline_completion_20260922
T07=/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922
T03_CODE=/home-mscluster/mbangie/t12-hpc/code/pilot120_t03_gf_ablation-20260923
ABLE_OUT=/home-mscluster/mbangie/t12-hpc/results/able_ix_five_seed-20260923
GOLD=/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922/data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl

echo "=== T07 TREE ==="
ls -lh "${EXP}"/*.jsonl "${EXP}"/*.json 2>/dev/null || true
echo "=== EMIT ==="
wc -l "${EXP}/06_raw_qwen_t07.predictions.jsonl" \
      "${EXP}/07_finetune_t07.predictions.jsonl" \
      "${EXP}/emit/t28_selected_adapter_llm/t28_selected_adapter_llm.predictions.jsonl" \
      "${EXP}/emit/direct_base_llm/direct_base_llm.predictions.jsonl" 2>/dev/null || true
echo "=== PACKETS ==="
find "${EXP}/packets" -type f 2>/dev/null | head
echo "=== JUDGE LOG ==="
find "${EXP}/judges" -name '*.log' 2>/dev/null | head
if [[ -d "${EXP}/judges" ]]; then
  find "${EXP}/judges" -name '*.server.log' -print -exec tail -n 40 {} \;
fi

# Ensure 07 exists from emit file
if [[ ! -s "${EXP}/07_finetune_t07.predictions.jsonl" ]]; then
  if [[ -s "${EXP}/emit/t28_selected_adapter_llm/t28_selected_adapter_llm.predictions.jsonl" ]]; then
    cp -f "${EXP}/emit/t28_selected_adapter_llm/t28_selected_adapter_llm.predictions.jsonl" \
      "${EXP}/07_finetune_t07.predictions.jsonl"
    echo "copied_07_from_emit"
  fi
fi

python3 - <<'PY'
import json
from pathlib import Path
from collections import Counter

def load(p):
    rows = []
    p = Path(p)
    if not p.exists():
        return rows
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows

def norm(v):
    t = str(v or "").strip().lower()
    if t in {"face_preserving_rejection", "reject", "refuse", "rejection"}:
        return "refuse"
    if t in {"clarify", "clarification", "ask"}:
        return "clarify"
    if t in {"execute", "act", "silently_resolve"}:
        return "execute"
    return t or "missing"

exp = Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922/t07_matched_baseline_completion_20260922")
gold = {r["record_id"]: r for r in load("/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922/data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl")}
ids = [l.strip() for l in (exp / "02_input_case_ids.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
preds = load(exp / "07_finetune_t07.predictions.jsonl")
print("FT_N", len(preds), "unique", len({p["record_id"] for p in preds}), "order_ok", [p["record_id"] for p in preds] == ids)
ok = sum(1 for p in preds if (not p.get("failed")) and norm(p.get("terminal_strategy")) == norm(gold[p["record_id"]].get("terminal_strategy")))
failed = sum(1 for p in preds if p.get("failed"))
conf = Counter()
for p in preds:
    g = norm(gold[p["record_id"]].get("terminal_strategy"))
    pr = "failed" if p.get("failed") else norm(p.get("terminal_strategy"))
    conf[(g, pr)] += 1
man = {}
mp = exp / "emit/t28_selected_adapter_llm/run_manifest.json"
if mp.exists():
    man = json.loads(mp.read_text(encoding="utf-8"))
route = {
    "system": "Fine-Tune",
    "n": 120,
    "exact_route_correct": ok,
    "failed_in_denominator": failed,
    "order_matches_frozen": [p["record_id"] for p in preds] == ids,
    "unique_ids": len({p["record_id"] for p in preds}),
    "temperature": man.get("temperature"),
    "seed": man.get("seed"),
    "confusion_gold_pred": {f"{a}->{b}": n for (a, b), n in sorted(conf.items())},
    "note": "Official two-judge not finished; 58442 failed at Gemma vLLM readiness.",
}
(exp / "09_finetune_t07_route_eval.json").write_text(json.dumps(route, indent=2) + "\n", encoding="utf-8")
print(json.dumps(route, indent=2))
PY

# Cancel stuck ABLE chain (DependencyNeverSatisfied after 58442 failed)
for jid in 58551 58552 58553 58554 58555; do
  scancel "${jid}" 2>/dev/null || true
done
echo "cancelled_stuck_able_jobs"

# Install patched T07 sbatch (longer timeout + bind model dir + skip emit)
cp -f /tmp/t07_matched_baseline.sbatch \
  "${T07}/cluster/pilot120_t07_matched_baseline_20260922/t07_matched_baseline.sbatch"
cp -f /tmp/able_ix_temp.sbatch \
  "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923/able_ix_temp.sbatch"
cp -f /tmp/submit_five_temps.sh \
  "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923/submit_five_temps.sh"
chmod +x "${T07}/cluster/pilot120_t07_matched_baseline_20260922/"*.sbatch \
         "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923/"*.sh \
         "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923/"*.sbatch

export T07_CODE_ROOT="${T07}"
export T07_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922
export GFV2_CONTAINER=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif
export GFV2_HF_HOME=/home-mscluster/mbangie/t12-hpc/hf-cache
export GFV2_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-hpc/training-site-packages
export A01_CONTAINER_SIF=/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif
export A02_READY_TIMEOUT_SECONDS=1800
export A01_MAX_MODEL_LEN=8192
export T07_GF_PREDS="${T07}/artifacts_t07/goal_first_manager_v2.predictions.jsonl"
export T07_BLIND_PREDS="${T07}/artifacts_t07/goal_first_context_blind_v2.predictions.jsonl"
export T07_DEGREE_PREDS="${T07}/artifacts_t07/degree_based_router_v2.predictions.jsonl"
export T07_TIMID_PREDS="${T07}/artifacts_t07/rich_conservative_manager_v2.predictions.jsonl"
export AFTERANY=0

if squeue -u mbangie -h | grep -E 'p120-t07' >/dev/null; then
  echo "t07_already_queued"
  NEW_T07=$(squeue -u mbangie -h -n p120-t07-match -o '%i' | head -1)
else
  bash "${T07}/cluster/pilot120_t07_matched_baseline_20260922/submit.sh"
  NEW_T07=$(awk -F'\t' '/t07_matched_baseline/{print $2; exit}' "${T07_OUTPUT}/submission.tsv")
fi
echo "new_t07=${NEW_T07}"

export T03_CODE_ROOT="${T03_CODE}"
export ABLE_OUTPUT="${ABLE_OUT}"
export AFTER_FIRST="${NEW_T07}"
export ABLE_SEEDS="1 2 3 4"
# afterany so a later judge failure does not kill the temperature chain
# first job still waits for the new T07 job to *start finishing*; use afterany not afterok
export AFTER_FIRST_KIND=afterany
# submit_five_temps.sh uses AFTER_FIRST as first dependency with afterok hardcoded.
# Override by editing env: we pass AFTER_FIRST and a patched submit that uses afterany.

# Patch: first dependency afterany so judge crash cannot freeze the five-temp chain again.
sed -i 's/dep_kind="afterok"/dep_kind="afterany"/' \
  "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923/submit_five_temps.sh"
# Do not scancel 58550 again inside submit (already gone); comment is fine.
# submit_five_temps still cancels 58550 only.
bash "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923/submit_five_temps.sh"

# Stage Fine-Tune artifacts for the analysis zip
STAGE=/tmp/p120_ft_add_20260923
rm -rf "${STAGE}"
mkdir -p "${STAGE}"
cp -f "${EXP}/07_finetune_t07.predictions.jsonl" "${STAGE}/" || true
cp -f "${EXP}/09_finetune_t07_route_eval.json" "${STAGE}/" || true
cp -f "${EXP}/emit/t28_selected_adapter_llm/run_manifest.json" "${STAGE}/finetune_run_manifest.json" || true
cp -f "${EXP}/emit/t28_selected_adapter_llm/t28_selected_adapter_llm.predictions.jsonl" "${STAGE}/" || true
tar -czf /tmp/p120_ft_add_20260923.tar.gz -C /tmp p120_ft_add_20260923
ls -lh /tmp/p120_ft_add_20260923.tar.gz
echo FIX_JOBS_DONE
squeue -u mbangie
