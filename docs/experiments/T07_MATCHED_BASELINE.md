# T0.7 matched baseline: six systems on Pilot-120

## Data and method

The input is the 120 frozen records in
[`source_canonical.jsonl`](../../data/annotations/pilot_120_v1/source_canonical.jsonl),
with [`pilot_120_final_gold.jsonl`](../../data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl)
for scoring. The evaluation contract is
[`pilot_120_v1.json`](../../configs/evaluation/pilot_120_v1.json); the
two-judge intent assessment uses the versioned protocol in
[`configs/evaluation/pilot120_intent_v1/`](../../configs/evaluation/pilot120_intent_v1/).
The final archive's `01_manifest.json`, emit `run_manifest.json` files, and
`SHA256_FINAL.json` identify the particular run, model, adapter, seed, and
input hashes. Use these run manifests for model identity; the older global
`selected_identities_v1.json` does not identify this completed run by itself.

Raw Qwen and Fine-Tune intent-box predictions used temperature 0.7, seed 0.
Goal-First, Degree, Timid, and Context-Blind predictions came from an earlier
T0.7 run and were reused; they were not freshly emitted in the final judging
job. Degree and Timid share Goal-First's written intent generation, so their
official intent count is inherited. The final ZIP is
[`t07_matched_baseline_completion_20260927_FINAL.zip`](../../research/pilot120/artifacts/t07_matched_baseline_completion_20260927_FINAL.zip)
(SHA-256 `34ca50e034ca37b617068bb50c734d12fa26282fb5eec563c11ead700163e491`).
The inherited streams are also in
[`p120_full_analysis_20260923.zip`](../../research/pilot120/artifacts/p120_full_analysis_20260923.zip)
(SHA-256 `0305b1e9ab062876ee6ee89778cc6028d2eaf01718b7dd0295944e7d9cb81a01`).

## Reproduce the saved score, without GPU inference

This PowerShell example extracts both archives into ignored `outputs/`. It
does not change the frozen ZIPs or case files. Use `python` instead of `py` if
that is your installed Python launcher.

```powershell
py scripts/release/check_repository.py
$replay = 'outputs/t07_replay'
New-Item -ItemType Directory -Force -Path $replay | Out-Null
py -m zipfile -e research/pilot120/artifacts/t07_matched_baseline_completion_20260927_FINAL.zip $replay
py -m zipfile -e research/pilot120/artifacts/p120_full_analysis_20260923.zip $replay
$exp = Join-Path $replay 't07_matched_baseline_completion_20260922'
$pred = Join-Path $replay 'temperature_ablation_existing/T0.7/predictions'
py scripts/score_t07_matched_baseline_20260922.py `
  --experiment-dir $exp `
  --gf-preds (Join-Path $pred 'goal_first_manager_v2.predictions.jsonl') `
  --degree-preds (Join-Path $pred 'degree_based_router_v2.predictions.jsonl') `
  --timid-preds (Join-Path $pred 'rich_conservative_manager_v2.predictions.jsonl') `
  --blind-preds (Join-Path $pred 'goal_first_context_blind_v2.predictions.jsonl')
Get-Content (Join-Path $exp 'FINAL_T07_SCOREBOARD.md')
```

On Linux, with Python available as `python3`:

```sh
python3 scripts/release/check_repository.py
mkdir -p outputs/t07_replay
python3 -m zipfile -e research/pilot120/artifacts/t07_matched_baseline_completion_20260927_FINAL.zip outputs/t07_replay
python3 -m zipfile -e research/pilot120/artifacts/p120_full_analysis_20260923.zip outputs/t07_replay
exp=outputs/t07_replay/t07_matched_baseline_completion_20260922
pred=outputs/t07_replay/temperature_ablation_existing/T0.7/predictions
python3 scripts/score_t07_matched_baseline_20260922.py \
  --experiment-dir "$exp" \
  --gf-preds "$pred/goal_first_manager_v2.predictions.jsonl" \
  --degree-preds "$pred/degree_based_router_v2.predictions.jsonl" \
  --timid-preds "$pred/rich_conservative_manager_v2.predictions.jsonl" \
  --blind-preds "$pred/goal_first_context_blind_v2.predictions.jsonl"
cat "$exp/FINAL_T07_SCOREBOARD.md"
```

The scorer writes a new completion timestamp and a TAR beside the extracted
experiment; these new files are a replay, not the frozen ZIP. Its scores were
reproduced from the tracked archives on 2026-09-27. For fresh model inference,
inspect [`submit.sh`](../../cluster/pilot120_t07_matched_baseline_20260922/submit.sh)
and its Slurm file. That historical launcher assumes the Wits account's
specific containers, checkpoint, selected T28 adapter, paths, and four existing
manager prediction files. Provision and verify those dependencies before
creating a new versioned run; do not submit the old job unchanged.

## Recorded result

| System | Exact route /120 | Two-judge intent /120 (exploratory) |
| --- | ---: | ---: |
| Raw Qwen | 96 | 106 |
| Fine-Tune | 92 | 112 |
| Goal-First | 56 | 117 |
| Degree | 57 | 117, shared Goal-First |
| Timid | 29 | 117, shared Goal-First |
| Context-Blind | 21 | 119 |

These are two different metrics. Strong written intent does not imply the
system chose the correct terminal route. The archived `21_FINAL_STATUS.json`
records 120 unique cases and retains failed rows in the denominator. The
evaluator policy does not authorize LLM judges to determine official
correctness; see the [governance finding](../PAPER_REPRODUCIBILITY.md#semantic-judge-governance-finding).
The matched-depth-5 control was **not run**; T0.3 is **not included**. Inspect
[CA-0007](../../research/pilot120/cases/CA-0007.json) or the
[case index](../../research/pilot120/INDEX.md) for source, gold, predictions,
and official case outputs.
