# One-turn clarification recovery

## Data and question

This is a follow-up on Pilot-120 gold-EXECUTE cases that the repaired
Goal-First system unnecessarily sent to CLARIFY. The primary cohort is 22
REFUSE-to-CLARIFY capability-intervention cases; the secondary cohort is all
26 post-capability CLARIFY and gold-EXECUTE cases. The experiment supplies a
**gold-consistent oracle answer** after the clarification and asks whether the
same system then chooses EXECUTE. It is an upper bound under an artificial
answer, not a measurement of natural user responses or clarification quality.
The frozen cohort, protocol, predictions, paired tables, and final summary
are in [`p120_full_analysis_20260923.zip`](../../research/pilot120/artifacts/p120_full_analysis_20260923.zip)
under `one_turn_recovery_20260922/`.

## Reproduce the saved summary

After following T0.7's extraction step, run:

```powershell
py scripts/one_turn_recovery_20260922.py score `
  --experiment-dir outputs/t07_replay/one_turn_recovery_20260922
Get-Content outputs/t07_replay/one_turn_recovery_20260922/FINAL_ONE_TURN_RECOVERY_SUMMARY.json
```

On Linux, use `python3` with the same `score --experiment-dir` arguments,
then read the summary in that extracted directory.

This CPU scoring command was run against the tracked archive extraction on
2026-09-27. Fresh GPU inference uses the versioned
[`cluster/pilot120_one_turn_recovery_20260922/`](../../cluster/pilot120_one_turn_recovery_20260922/README.md)
contract, its original model/container environment, and a new output location.
Its `freeze`, `run`, and `score` modes are documented by
`py scripts/one_turn_recovery_20260922.py --help` and the archived manifest.

## Recorded result and limit

| Cohort | Seed 0 recovered to EXECUTE | Seed 1 recovered to EXECUTE |
| --- | ---: | ---: |
| Primary 22 | 13/22 | 16/22 |
| Secondary 26 | 16/26 | 17/26 |

First-turn exact routing remains **83/120**; first-turn immediate EXECUTE on
gold-EXECUTE remains **46/76**. The interaction-level one-turn success figures
are **62/76** and **63/76** for seeds 0 and 1, respectively. These are
separate from first-turn routing and must not be substituted for it. Seed 0's
three empty-route rows remain in the denominator. Seeds repeat the same
cases; do not pool them as 52 independent cases. The archived summary records
paired McNemar p-values 0.388 and 0.180, so this small follow-up does not
establish a reliable paired improvement over its matched control.
