# T27C — Task-Conditioned Partial-Schema Prediction

**Status: BLOCKED (live sealed prediction gates failed)**

Author: Mohammed Bangie — 2610990  
Ticket: T27C  
ADR: `docs/decisions/ADR_T27C_task_conditioned_partial_schema_prediction.md`  
Evidence: `configs/model/evidence/t27c_task_conditioned_smoke.json`

## Verdict

Live job **7054** (`t12-qlora-task-conditioned-20260723T105312Z-f9e252c`) completed
training/resume/mechanics and independently verified (`VERIFY_PASSED`), but **0/60**
sealed task calls were parse-valid because constrained decoding could not initialise
(`lm-format-enforcer_transformers_integration_unavailable`). No unconstrained
fallback was used. `selected_adapter` remains null; **T28 must not begin**.

Follow-on constraint fixes (core TokenEnforcer, disk tokenizer cache, Apptainer
`T12_TRAINING_SITE_PACKAGES`) are on the branch, but sealed GPU evals after those
fixes hung post-train before writing final result JSON and were cancelled.

## What passed locally / on cluster mechanics

| Gate | Result |
|------|--------|
| Task registry / field registry / assembler | Implemented + unit-tested |
| Datasets 192→470 / diagnostic 16 / sealed 12 | Built; leakage exclusions applied |
| Real 4-bit QLoRA + shared adapter | PASS (job 7054) |
| Full checkpoint / resume | PASS |
| Base frozen; adapter not selected | PASS |
| T27 6059 / T27B 6382 evidence | Preserved |

## What failed

| Gate | Result |
|------|--------|
| Constraint initialisation on sealed gen (7054) | FAIL (stock transformers integration import) |
| Task parse / schema / assembly accept rates | FAIL (0 valid parses) |
| Adapter≠base on sealed outputs | FAIL (both empty/rejected) |

## Official identities (unchanged)

- `selected_adapter = null`
- `selected_model_strategy = null`
- `valid_for_official_use = false`
- `t28_may_begin = false`

## Next recommended task

Debug and finish **constrained sealed generation** on cluster (confirm cache hit +
non-hanging `prefix_allowed_tokens_fn` generate path), then re-run
`qlora_task_conditioned_smoke` once and replace this evidence only if gates pass.
