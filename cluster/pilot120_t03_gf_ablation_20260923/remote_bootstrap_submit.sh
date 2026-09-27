#!/usr/bin/env bash
# Score existing temp emits, install T0.3 job, submit after 58442, pack analysis archive.
set -euo pipefail

FIX=/home-mscluster/mbangie/t12-hpc/code/pilot120_fix_emit-20260915
FC=/home-mscluster/mbangie/t12-hpc/code/final_close-20260913
T07=/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922
T03_CODE=/home-mscluster/mbangie/t12-hpc/code/pilot120_t03_gf_ablation-20260923
T03_OUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_t03_gf_ablation-20260923
T07_OUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922
REC=/home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922/one_turn_recovery_20260922
EXP_T07="${T07_OUT}/t07_matched_baseline_completion_20260922"
PRIO=/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915
STAGE=/tmp/p120_full_analysis_pack_20260923

echo "=== SQUEUE ==="
squeue -u mbangie
echo "=== 58442 ==="
sacct -j 58442 --format=JobID,JobName,State,Elapsed,ExitCode,End,NodeList -P

# --- install T0.3 code tree as a view of the unified fix-stack ---
mkdir -p "${T03_CODE}" "${T03_OUT}"
if [[ ! -e "${T03_CODE}/.installed" ]]; then
  rsync -a --delete \
    --exclude '.git' \
    --exclude 'outputs' \
    --exclude 'latest results' \
    "${FIX}/" "${T03_CODE}/"
  touch "${T03_CODE}/.installed"
fi
cp -f /tmp/score_gf_temp_ablation_20260923.py "${T03_CODE}/scripts/score_gf_temp_ablation_20260923.py"
mkdir -p "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923"
cp -f /tmp/t03_gf_ablation.sbatch "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923/t03_gf_ablation.sbatch"
cp -f /tmp/t03_submit.sh "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923/submit.sh"
chmod +x "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923/"*.sh \
         "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923/"*.sbatch
# freeze files
mkdir -p "${T03_OUT}/t03_gf_ablation_able_ix_20260923"
cp -f /tmp/00_PROTOCOL_FREEZE.md "${T03_OUT}/t03_gf_ablation_able_ix_20260923/00_PROTOCOL_FREEZE.md" || true
test -f "${T03_CODE}/scripts/evaluate_goal_first_manager_v2.py"
test -f "${T03_CODE}/scripts/score_gf_temp_ablation_20260923.py"
echo "t03_code_ok"

python3 - <<'PY'
import json, re
from pathlib import Path

def load_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

def norm(v):
    t = str(v or "").strip().lower()
    if t in {"face_preserving_rejection", "reject", "refuse", "rejection"}:
        return "refuse"
    if t in {"clarify", "clarification", "ask"}:
        return "clarify"
    if t in {"execute", "act", "silently_resolve"}:
        return "execute"
    return t or "missing"

_CONTENT_RE = re.compile(r"[a-z0-9]+", re.I)
_NEG = {"not", "no", "never", "dont", "don't", "cannot", "cant", "can't", "refuse", "forbidden"}

def content_tokens(text):
    return {t.lower() for t in _CONTENT_RE.findall(text or "") if len(t) > 1}

def jaccard(a, b):
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def polarity_flip(pred, ref):
    pt, rt = content_tokens(pred), content_tokens(ref)
    return bool(pt & _NEG) != bool(rt & _NEG) and bool(pt & rt)

def intent_pass(summary, gold, thr=0.18):
    refs = [str(gold.get("reference_A_intent_text") or ""), str(gold.get("reference_B_intent_text") or "")]
    best = 0.0
    for ref in refs:
        if not ref.strip() or polarity_flip(summary, ref):
            continue
        best = max(best, jaccard(content_tokens(summary), content_tokens(ref)))
    return best >= thr

root = Path("/home-mscluster/mbangie/t12-hpc/code/pilot120_fix_emit-20260915")
if not (root / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl").exists():
    root = Path("/home-mscluster/mbangie/t12-hpc/code/final_close-20260913")
gold_rows = load_jsonl(root / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl")
gold = {r["record_id"]: r for r in gold_rows}
ids = [r["record_id"] for r in gold_rows]
refs_path = (
    root / "pilot120_intent_evaluation_20260902/pilot120_intent_evaluation_20260902"
    / "validation/self_contained_rebuild/data/intent_gold_references_120.jsonl"
)
if not refs_path.exists():
    refs_path = root / "data/annotations/pilot_120_v1/intent_gold_references_120.jsonl"
refs = {r["record_id"]: r for r in load_jsonl(refs_path)} if refs_path.exists() else {}
for rid, row in list(gold.items()):
    if rid in refs:
        row = dict(row)
        row["reference_A_intent_text"] = refs[rid].get("reference_A_intent_text")
        row["reference_B_intent_text"] = refs[rid].get("reference_B_intent_text")
        gold[rid] = row
print("GOLD", len(gold), "REFS", len(refs), "REFS_PATH", refs_path)

def score(path):
    path = Path(path)
    rows = {r["record_id"]: r for r in load_jsonl(path)}
    if not rows:
        return {"exists": path.exists(), "n": 0, "path": str(path)}
    route = intent = failed = 0
    for rid in ids:
        p = rows.get(rid) or {}
        if p.get("failed"):
            failed += 1
            continue
        if norm(p.get("terminal_strategy")) == norm(gold[rid].get("terminal_strategy")):
            route += 1
        if intent_pass(str(p.get("intent_summary") or ""), gold[rid]):
            intent += 1
    man = {}
    mp = path.resolve().parents[1] / "run_manifest.json"
    if mp.exists():
        man = json.loads(mp.read_text(encoding="utf-8"))
    return {
        "path": str(path),
        "n": len(rows),
        "route": route,
        "intent_screen": intent,
        "failed": failed,
        "temperature": man.get("temperature"),
        "seed": man.get("seed"),
        "status": man.get("status"),
    }

prio = Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915")
table = {}
for T in ["T0.0", "T0.3", "T0.5", "T0.7", "T1.0"]:
    table[T] = score(prio / T / "predictions" / "goal_first_manager_v2.predictions.jsonl")
    print("SCORE", T, json.dumps(table[T]))

ft = Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922/t07_matched_baseline_completion_20260922/emit/t28_selected_adapter_llm/t28_selected_adapter_llm.predictions.jsonl")
print("FT_N", sum(1 for line in ft.open() if line.strip()) if ft.exists() else 0)
out = Path("/tmp/able_ix_existing_scores.json")
out.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
print("WROTE", out)
PY

# --- submit T0.3; do not touch running 58442 ---
STATE="$(sacct -j 58442 --format=State --noheader -X | awk '{print $1}' | head -1 || true)"
echo "58442_state=${STATE}"
if squeue -u mbangie -h | grep -E 'p120-t03' >/dev/null; then
  echo "t03_already_queued"
else
  export T03_CODE_ROOT="${T03_CODE}"
  export T03_OUTPUT="${T03_OUT}"
  export GFV2_CONTAINER=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif
  export GFV2_HF_HOME=/home-mscluster/mbangie/t12-hpc/hf-cache
  export GFV2_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-hpc/training-site-packages
  export T03_SEEDS="1 2 3"
  if [[ "${STATE}" == "RUNNING" || "${STATE}" == "PENDING" ]]; then
    export AFTEROK=58442
  else
    export AFTEROK=0
  fi
  bash "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923/submit.sh"
fi

# --- pack one analysis archive of everything currently on disk ---
rm -rf "${STAGE}"
mkdir -p "${STAGE}/one_turn_recovery_20260922" \
         "${STAGE}/t07_matched_baseline_completion_20260922" \
         "${STAGE}/t03_gf_ablation_able_ix_20260923" \
         "${STAGE}/temperature_ablation_existing" \
         "${STAGE}/logs"

if [[ -d "${REC}" ]]; then
  rsync -a "${REC}/" "${STAGE}/one_turn_recovery_20260922/"
fi

# T07: keep freeze + raw + logs; snapshot FT as INPROGRESS if 07 not complete
if [[ -d "${EXP_T07}" ]]; then
  rsync -a --exclude 'emit/t28_selected_adapter_llm/*.predictions.jsonl' \
    "${EXP_T07}/" "${STAGE}/t07_matched_baseline_completion_20260922/"
  mkdir -p "${STAGE}/t07_matched_baseline_completion_20260922/emit/t28_selected_adapter_llm"
  if [[ -f "${EXP_T07}/07_finetune_t07.predictions.jsonl" ]]; then
    n="$(wc -l < "${EXP_T07}/07_finetune_t07.predictions.jsonl" | tr -d ' ')"
    if [[ "${n}" -ge 120 ]]; then
      cp -f "${EXP_T07}/07_finetune_t07.predictions.jsonl" \
        "${STAGE}/t07_matched_baseline_completion_20260922/07_finetune_t07.predictions.jsonl"
    fi
  fi
  if [[ -f "${EXP_T07}/emit/t28_selected_adapter_llm/t28_selected_adapter_llm.predictions.jsonl" ]]; then
    cp -f "${EXP_T07}/emit/t28_selected_adapter_llm/t28_selected_adapter_llm.predictions.jsonl" \
      "${STAGE}/t07_matched_baseline_completion_20260922/emit/t28_selected_adapter_llm/t28_selected_adapter_llm.INPROGRESS.predictions.jsonl"
  fi
fi

for T in T0.0 T0.3 T0.5 T0.7 T1.0; do
  mkdir -p "${STAGE}/temperature_ablation_existing/${T}"
  if [[ -d "${PRIO}/${T}" ]]; then
    rsync -a --include 'run_manifest.json' --include 'progress.json' \
      --include 'predictions/' --include 'predictions/*.jsonl' \
      --include 'evaluations/' --include 'evaluations/*.json' \
      --exclude '*' \
      "${PRIO}/${T}/" "${STAGE}/temperature_ablation_existing/${T}/" || true
  fi
done
cp -f /tmp/able_ix_existing_scores.json "${STAGE}/temperature_ablation_existing/ABLE_IX_EXISTING_SCORES.json" || true
cp -f /tmp/00_PROTOCOL_FREEZE.md "${STAGE}/t03_gf_ablation_able_ix_20260923/00_PROTOCOL_FREEZE.md" || true
cp -f /home-mscluster/mbangie/t12-hpc/logs/p120-t07-match-58442.out "${STAGE}/logs/p120-t07-match-58442.out.partial" || true
cp -f /home-mscluster/mbangie/t12-hpc/logs/p120-1turn-rec-58441.out "${STAGE}/logs/" || true

python3 - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path
stage = Path("/tmp/p120_full_analysis_pack_20260923")
scores = {}
sp = Path("/tmp/able_ix_existing_scores.json")
if sp.exists():
    scores = json.loads(sp.read_text(encoding="utf-8"))
t03 = Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_t03_gf_ablation-20260923/submission.tsv")
sub = t03.read_text(encoding="utf-8") if t03.exists() else ""
ft = Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922/t07_matched_baseline_completion_20260922/emit/t28_selected_adapter_llm/t28_selected_adapter_llm.predictions.jsonl")
ft_n = sum(1 for line in ft.open() if line.strip()) if ft.exists() else 0
status = {
    "packed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "one_zip_note": "This archive is the single analysis pack. Fine-Tune/official T0.7 judges and new T0.3 seeds are live jobs, not invented numbers.",
    "recovery_job": {"id": 58441, "state": "COMPLETED"},
    "t07_job": {"id": 58442, "finetune_rows_now": ft_n, "official_two_judge": "waits_for_finetune_inside_58442"},
    "t03_submission": sub.strip(),
    "able_ix_existing_fixstack_scores": scores,
    "finetune": "RESULTS IN PROGRESS" if ft_n < 120 else "emit_complete_check_07_file",
    "t03_new_seeds": "RESULTS IN PROGRESS (pre-specified seeds 1 2 3; all retained)",
}
(stage / "STATUS.md").write_text("# Pilot-120 analysis pack\n\n" + json.dumps(status, indent=2) + "\n", encoding="utf-8")
print(json.dumps(status, indent=2))
PY

cd /tmp
tar -czf /tmp/p120_full_analysis_20260923.tar.gz -C /tmp p120_full_analysis_pack_20260923
ls -lh /tmp/p120_full_analysis_20260923.tar.gz
echo PACK_AND_SUBMIT_DONE
squeue -u mbangie
