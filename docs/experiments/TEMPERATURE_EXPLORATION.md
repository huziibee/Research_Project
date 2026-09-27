# Existing Goal-First temperature streams

## Data and scope

The full-analysis ZIP holds one existing seed-0, 120-case Goal-First prediction
stream at each temperature 0.0, 0.3, 0.5, 0.7, and 1.0 under
`temperature_ablation_existing/`. These are saved exploratory observations,
not the later five-seed ABLE IX study. The gold is the frozen Pilot-120 JSONL.
The same ZIP contains `ABLE_IX_EXISTING_SCORES.json` and each run manifest.

To rescore one extracted stream after the T0.7 guide's extraction command:

```powershell
py scripts/score_gf_temp_ablation_20260923.py `
  --root . `
  --pred outputs/t07_replay/temperature_ablation_existing/T0.7/predictions/goal_first_manager_v2.predictions.jsonl `
  --out outputs/t07_replay/T0.7_rescore.json `
  --temperature 0.7 --seed 0 --label T0.7
```

On Linux, use `python3` with the same scorer flags and extracted paths.

This command was run on 2026-09-27 and returned **56/120 exact route** for
T0.7. The recorded exact-route counts for T0.0, T0.3, T0.5, T0.7, and T1.0
are **49, 53, 51, 56, 44 /120**, respectively. T0.0, T0.3, and T0.5 each
have one failed row retained in the denominator. The scorer's `intent_screen`
is an automatic text-overlap screen, **not** official two-judge intent.

The later five-temperature, five-seed ABLE IX queue is described by
[`cluster/pilot120_t03_gf_ablation_20260923/`](../../cluster/pilot120_t03_gf_ablation_20260923/).
Its jobs were still running or dependency-queued at the 2026-09-27 check.
Check Slurm and final row-level artifacts before writing a completed ABLE IX
result; do not treat these five older seed-0 streams as the finished study.
