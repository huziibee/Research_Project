# Up-to-five-round oracle-consistent clarification recovery

This is the completed [one-turn recovery](ONE_TURN_RECOVERY.md) study's
**answered-condition loop**, whose configured maximum was five clarification
depths. The name “one-turn” describes the first oracle answer; if the system
kept asking, the runner repeated the same gold-consistent intent restatement
until a non-CLARIFY route, failure, or depth 5. The matched control replayed
the original first-turn input at depth 0. This is exploratory; repeated oracle
answers and the different interaction depth prevent a matched-depth causal
claim about clarification dialogue.

## Source, execution, and replay

- Frozen input: [Pilot-120 source](../../data/annotations/pilot_120_v1/source_canonical.jsonl)
  and [gold](../../data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl).
- Cohorts: 22 primary cases that moved REFUSE to CLARIFY after capability
  intervention; 26 secondary cases including four already-CLARIFY cases.
  Their ID lists, oracle messages, protocol, predictions, and both seed
  summaries are inside
  [`p120_full_analysis_20260923.zip`](../../research/pilot120/artifacts/p120_full_analysis_20260923.zip)
  under `one_turn_recovery_20260922/` (ZIP SHA-256
  `0305b1e9ab062876ee6ee89778cc6028d2eaf01718b7dd0295944e7d9cb81a01`).
  The exact members are `02_primary_cohort_22.jsonl`,
  `03_secondary_cohort_26.jsonl`, `04_oracle_responses.jsonl`,
  `06_answered_predictions_seed0.jsonl`,
  `12_answered_predictions_seed1.jsonl`, `09_summary_seed0.json`,
  `14_summary_seed1.json`, and `FINAL_ONE_TURN_RECOVERY_SUMMARY.json`.
- The frozen `01_frozen_manifest.json` specifies Qwen3-8B revision
  `b968826d9c46dd6066d109eabc6255188de91218`, temperature 0.7,
  seeds 0 and 1, capability judge, router, and input hashes. The run code is
  [`one_turn_recovery_20260922.py`](../../scripts/one_turn_recovery_20260922.py)
  with [`cluster launcher`](../../cluster/pilot120_one_turn_recovery_20260922/README.md).
- Recompute the saved summary after extracting the ZIP to an ignored folder:

```sh
python -m zipfile -e research/pilot120/artifacts/p120_full_analysis_20260923.zip outputs/recovery_replay
python scripts/one_turn_recovery_20260922.py score --experiment-dir outputs/recovery_replay/one_turn_recovery_20260922
```

The scorer reads saved predictions; it does not run the model. Verify the
archive and source hashes first with `python scripts/release/check_repository.py`.

## Both repeats

| Outcome | Seed 0 | Seed 1 |
| --- | ---: | ---: |
| Primary recovered to EXECUTE /22 | 13 | 16 |
| Secondary recovered to EXECUTE /26 | 16 | 17 |
| Primary still CLARIFY /22 | 5 | 5 |
| Secondary still CLARIFY /26 | 5 | 7 |
| Primary REFUSE /22 | 1 | 1 |
| Secondary REFUSE /26 | 2 | 2 |
| Empty/invalid terminal route /26 | 3 | 0 |

The persistent CLARIFY and REFUSE outcomes count as non-recovery. Seed 0's
three invalid terminal routes also remain in the denominator. The five-depth
cap was actually reached by 6/26 answered rows at seed 0 and 8/26 at seed 1;
the other rows stopped earlier on a terminal route or failure. Seeds are
repeats on the **same cases**, not 52 independent observations. The
interaction-level numbers are 62/76 and 63/76; first-turn exact route remains
83/120 and first-turn immediate EXECUTE on gold-EXECUTE remains 46/76.

## Why three seed-0 cases had no valid route

| Case | Seed-0 depth path | Recorded failure | Seed-1 contrast |
| --- | --- | --- | --- |
| [CA-0702](../../research/pilot120/cases/CA-0702.json) | depth 1: empty route | `bad_intent_summary` on all three analysis attempts; constrained final ended at `maximum_token` | CLARIFY at depth 1, EXECUTE at depth 2 |
| [CA-0733](../../research/pilot120/cases/CA-0733.json) | depth 1: CLARIFY; depth 2: empty route | depth-2 analysis failed `bad_intent_summary` on all attempts; constrained final ended at `maximum_token` | CLARIFY through depth 3, EXECUTE at depth 4 |
| [CA-0778](../../research/pilot120/cases/CA-0778.json) | depth 1: CLARIFY; depth 2: empty route | depth-2 attempts recorded `bad_intent_summary`, `bad_pilot_ambiguity_types`, then `bad_intent_summary`; constrained final ended at `maximum_token` | EXECUTE at depth 1 |

The parser requires a nonempty `intent_summary` under 500 characters. In the
saved final constrained generation for each failed seed-0 step, termination
was `maximum_token`, and the extractable JSON candidate was a nested
`value/status` object with no `intent_summary`; the validator therefore
returned `bad_intent_summary`. The runner skipped capability adjudication
after the failed analysis and recorded an empty terminal route. The archive
does not retain every earlier raw attempt, so the recorded validation codes
are the limit of diagnosis for attempts 1–2. The complete
[technical diagnosis and versioned rerun plan](DEPTH_FIVE_TECHNICAL_RERUN_V1.md)
classifies the final failures as incomplete generation at the token cap; the
parser correctly rejects those fragments. This is not evidence that gold
changed or that those cases were intrinsically unrecoverable.

**Claim limit:** oracle-consistent repeated answers and the <=5-depth cap do
not measure natural user behaviour, question quality, or an equal-depth
treated-versus-control effect. Do not call this a matched-depth causal result
or substitute recovery success for the unchanged first-turn routing score.
