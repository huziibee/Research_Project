#!/usr/bin/env bash
set -euo pipefail
EXP=/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922/t07_matched_baseline_completion_20260922
REC=/home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922/one_turn_recovery_20260922
STAGE=/tmp/p120_results_pack_20260923
rm -rf "$STAGE"
mkdir -p "$STAGE/t07_matched_baseline_completion_20260922" \
         "$STAGE/one_turn_recovery_20260922" \
         "$STAGE/logs"

# Copy everything except leave a note that FT is still writing; copy current FT snapshot too.
rsync -a "$REC/" "$STAGE/one_turn_recovery_20260922/"
rsync -a --exclude 'emit/t28_selected_adapter_llm/*.predictions.jsonl' \
  "$EXP/" "$STAGE/t07_matched_baseline_completion_20260922/"
# snapshot in-progress FT separately so zip is frozen
mkdir -p "$STAGE/t07_matched_baseline_completion_20260922/emit/t28_selected_adapter_llm"
if [[ -f "$EXP/emit/t28_selected_adapter_llm/t28_selected_adapter_llm.predictions.jsonl" ]]; then
  cp -f "$EXP/emit/t28_selected_adapter_llm/t28_selected_adapter_llm.predictions.jsonl" \
    "$STAGE/t07_matched_baseline_completion_20260922/emit/t28_selected_adapter_llm/t28_selected_adapter_llm.INPROGRESS.predictions.jsonl"
fi
if [[ -f "$EXP/emit/t28_selected_adapter_llm/run_manifest.json" ]]; then
  cp -f "$EXP/emit/t28_selected_adapter_llm/run_manifest.json" \
    "$STAGE/t07_matched_baseline_completion_20260922/emit/t28_selected_adapter_llm/"
fi
cp -f /home-mscluster/mbangie/t12-hpc/logs/p120-1turn-rec-58441.out "$STAGE/logs/" || true
cp -f /home-mscluster/mbangie/t12-hpc/logs/p120-1turn-rec-58441.err "$STAGE/logs/" || true
cp -f /home-mscluster/mbangie/t12-hpc/logs/p120-t07-match-58442.out "$STAGE/logs/p120-t07-match-58442.out.partial" || true

python3 - <<'PY'
import json, csv
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

exp = Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922/t07_matched_baseline_completion_20260922")
stage = Path("/tmp/p120_results_pack_20260923/t07_matched_baseline_completion_20260922")
gold_p = Path("/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922/data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl")
ids = [l.strip() for l in (exp / "02_input_case_ids.txt").read_text().splitlines() if l.strip()]
gold = {}
for line in gold_p.read_text(encoding="utf-8").splitlines():
    if line.strip():
        r = json.loads(line)
        gold[r["record_id"]] = r

def norm(v):
    t = str(v or "").strip().lower()
    if t in {"face_preserving_rejection", "reject", "refuse", "rejection"}:
        return "refuse"
    if t in {"clarify", "clarification", "ask"}:
        return "clarify"
    if t in {"execute", "act", "silently_resolve"}:
        return "execute"
    return t or "missing"

preds = [json.loads(l) for l in (exp / "06_raw_qwen_t07.predictions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
order_ok = [p["record_id"] for p in preds] == ids
ok = sum(
    1
    for p in preds
    if (not p.get("failed"))
    and norm(p.get("terminal_strategy")) == norm(gold[p["record_id"]].get("terminal_strategy"))
)
failed = sum(1 for p in preds if p.get("failed"))
conf = Counter()
for p in preds:
    g = norm(gold[p["record_id"]].get("terminal_strategy"))
    pr = "failed" if p.get("failed") else norm(p.get("terminal_strategy"))
    conf[(g, pr)] += 1
man = json.loads((exp / "emit/direct_base_llm/run_manifest.json").read_text(encoding="utf-8"))
evalj = {}
evp = exp / "emit/direct_base_llm/direct_base_llm.eval.json"
if evp.exists():
    evalj = json.loads(evp.read_text(encoding="utf-8"))

route_eval = {
    "system": "Raw Qwen",
    "n": 120,
    "exact_route_correct": ok,
    "failed_in_denominator": failed,
    "order_matches_frozen": order_ok,
    "unique_ids": len({p["record_id"] for p in preds}),
    "temperature": man.get("temperature"),
    "seed": man.get("seed"),
    "confusion_gold_pred": {f"{a}->{b}": n for (a, b), n in sorted(conf.items())},
    "note": "Fine-Tune routing IN PROGRESS on job 58442; official two-judge not started yet.",
}
(stage / "08_raw_qwen_t07_route_eval.json").write_text(json.dumps(route_eval, indent=2) + "\n", encoding="utf-8")
(stage / "09_finetune_t07_route_eval.json").write_text(
    json.dumps(
        {
            "system": "Fine-Tune",
            "status": "IN_PROGRESS",
            "job": 58442,
            "n_done_at_pack_time": sum(
                1
                for _ in (exp / "emit/t28_selected_adapter_llm/t28_selected_adapter_llm.predictions.jsonl").open()
            )
            if (exp / "emit/t28_selected_adapter_llm/t28_selected_adapter_llm.predictions.jsonl").exists()
            else 0,
            "n_expected": 120,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)

status = {
    "packed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "recovery_job": {"id": 58441, "state": "COMPLETED", "exit": "0:0"},
    "t07_job": {"id": 58442, "state": "RUNNING", "phase": "finetune_intent_box_t07"},
    "raw_qwen": {
        "predictions": 120,
        "exact_route": f"{ok}/120",
        "failed_rows": failed,
        "temperature": man.get("temperature"),
        "seed": man.get("seed"),
        "order_ok": order_ok,
    },
    "finetune": "RESULTS IN PROGRESS — do not treat partial file as official",
    "official_two_judge": "NOT STARTED (waits for Fine-Tune emit to finish inside 58442)",
    "no_errors_requiring_resubmit": True,
    "notes": [
        "Raw emit complete and copied to 06_raw_qwen_t07.predictions.jsonl",
        "Fine-Tune emit running; snapshot only in INPROGRESS file",
        "Official judging, scoreboard, paired stats still pending job 58442",
        "Recovery experiment 58441 completed successfully",
    ],
}
(stage / "STATUS_IN_PROGRESS.md").write_text(
    "# T0.7 pack status\n\n"
    + json.dumps(status, indent=2)
    + "\n\nFine-Tune: RESULTS IN PROGRESS.\nOfficial two-judge: not started.\n",
    encoding="utf-8",
)
print(json.dumps(status, indent=2))
print("RAW_ROUTE", ok, "/120 failed", failed, "order", order_ok)
print("CONF", dict(conf))
PY

# recovery sanity
python3 - <<'PY'
import json
from pathlib import Path
rec = Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922/one_turn_recovery_20260922")
d = json.load(open(rec / "FINAL_ONE_TURN_RECOVERY_SUMMARY.json"))
print("REC_OK", "seed0" in d, "seed1" in d)
print(json.dumps(d.get("seed0", {}).get("primary"), indent=2)[:1200])
print(json.dumps(d.get("seed0", {}).get("secondary"), indent=2)[:800])
print(json.dumps(d.get("seed0", {}).get("interaction_level_one_turn_success"), indent=2)[:800])
print("mcnemar", d.get("seed0", {}).get("mcnemar_exact"))
print("seed1_primary", d.get("seed1", {}).get("primary"))
# file completeness
need = [
    "05_control_predictions_seed0.jsonl","06_answered_predictions_seed0.jsonl",
    "11_control_predictions_seed1.jsonl","12_answered_predictions_seed1.jsonl",
    "FINAL_ONE_TURN_RECOVERY_SUMMARY.json",
]
for n in need:
    p = rec / n
    print(n, p.exists(), sum(1 for line in p.open() if line.strip()) if p.suffix==".jsonl" else "na")
PY

cd /tmp
tar -czf /tmp/p120_results_in_progress_20260923.tar.gz -C /tmp p120_results_pack_20260923
ls -lh /tmp/p120_results_in_progress_20260923.tar.gz
echo PACK_DONE
