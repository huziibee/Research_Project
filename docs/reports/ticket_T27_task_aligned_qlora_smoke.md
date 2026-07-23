# T27 task-aligned structured QLoRA smoke

Date: 2026-07-23
Author: Mohammed Bangie (2610990)

## Verdict

Live task-aligned QLoRA smoke is **BLOCKED** on structured-output acceptance.

- mechanics_status: **PASS**
- task_aligned_training_status: **PASS**
- structured_output_smoke_status: **BLOCKED** (0/4 accepted strict semantic JSON)
- ticket_status: **BLOCKED**

Do **not** begin T28. Do not select the smoke adapter.

Prior mechanics smoke evidence under `configs/model/evidence/qlora_smoke_v1/` is retained.

## Identities (unchanged)

| Field | Value |
|---|---|
| `selected_base_model` | `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218` |
| `selected_adapter` | `null` |
| `selected_model_strategy` | `null` |
| `valid_for_official_use` | `false` |

## Live run (job 6059)

| Field | Value |
|---|---|
| Run ID | `t12-qlora-task-aligned-20260723T074715Z-991732e` |
| Source commit | `991732ea08e0d4db7b873cdc42fbcacd3fc5aac4` |
| Slurm job | `6059` |
| Node | `mscluster111` (scheduler-selected; no permanent nodelist pin) |
| Mode | `real_cluster_training` |
| Operator verify | `VERIFY_PASSED` |
| Runtime | 96.026 s |
| Wall elapsed | `00:02:28` |
| Peak VRAM | 24163487744 bytes (~22.5 GiB) |
| Frozen params | 4717851648 |
| Trainable adapter params | 7667712 |
| Train records | 64 (`source_train`) |
| Val records | 4 (`source_dev`) |
| Full resume | all component booleans true |
| Loss | decreasing 4.78 → 2.69 over 8 supervised-mask steps |
| Structured accepted | **0 / 4** (all `schema_invalid`) |
| Adapter vs base differ | 4 / 4 |

## Failed precursor (job 6058)

`mscluster108` Apptainer setgroups permission denied. Preserved in
`configs/model/evidence/t27_task_aligned_qlora_smoke_job6058_fail.json`.
Correction: exclude `mscluster107,mscluster108` (still no permanent pin).

## Defect-to-file map (corrected)

| Defect | Pre-fix location | Correction |
|---|---|---|
| Command reconstruction | `qlora_smoke.py` labels=input_ids on command | `token_loss_masking.py` + task-aligned loop |
| Loss masks unused | packaging only | real labels tensor in training loop |
| Braces-only acceptance | inference smoke heuristic | `structured_output_validation.py` |
| Incomplete resume | adapter-only reload | `qlora_checkpoint.py` full blob |
| Silent mock fallback | live deps-missing path | `require_real_mode` hard fail |
| Stale env manifest | planned_unverified values | `t12_cluster_training_task_aligned_v1.json` |
| Permanent node pin | `nodelist=mscluster111` | removed; exclude incompatible nodes only |

## Compact evidence

- `configs/model/evidence/t27_task_aligned_qlora_smoke.json`
- Adapter/checkpoint weights **not** committed

## Next recommended task

Model/training strategy review for structured-output emission under the
production semantic schema (partial-target training → full-schema inference
mismatch). Do not tune the frozen four held-out IDs.
