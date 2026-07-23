# T27 task-aligned structured QLoRA smoke

Date: 2026-07-23
Author: Mohammed Bangie (2610990)

## Status

Implementation complete locally. Live cluster evidence pending / to be filled after
`python scripts/t12_cluster_job.py --run qlora_task_aligned_smoke --poll --pull`.

Prior mechanics smoke evidence under `configs/model/evidence/qlora_smoke_v1/` is retained.

## Defect-to-file map (pre-fix)

| Defect | Location |
|---|---|
| Command-token reconstruction | `qlora_smoke.py` `run_real_qlora_smoke` used `labels=input_ids` on command text |
| Loss masks reported but unused | `training_target_packaging.py` weights unused by real loss |
| Weak braces acceptance | `run_real_inference_and_diff_smoke` `structured_output_has_object` |
| Incomplete resume | adapter reload only; new AdamW after resume |
| Silent mock fallback | `run_smoke_training` when deps missing |
| Stale env manifest | `t12_cluster_training.json` planned_unverified values |
| Permanent node pin | `t12_job_profiles.json` `nodelist=mscluster111` |

## Corrections

- Training-example contract + structured-target serialiser + real token masks
- Full checkpoint/resume component booleans
- Strict structured-output validator (no braces-only pass)
- Dataset `qlora_task_aligned_smoke_v2` (64 train) + frozen 4-record `source_dev` val
- Live profile `qlora_task_aligned_smoke` (no nodelist pin; mock separate)
- Environment identity `t12_cluster_training_task_aligned_v1.json`

## Identities (unchanged)

- `selected_base_model` = Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218
- `selected_adapter` = null
- `selected_model_strategy` = null
- `valid_for_official_use` = false
