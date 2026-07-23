# T27C — Task-Conditioned Partial-Schema Prediction

**Status: IMPLEMENTATION COMPLETE / LIVE RESULTS TBD**

Author: Mohammed Bangie — 2610990  
Ticket: T27C  
ADR: `docs/decisions/ADR_T27C_task_conditioned_partial_schema_prediction.md`

## Verdict (local)

Local contracts, datasets, assembler, constrained-decoding policy, and mock
orchestrator evidence finalisation are implemented. The live cluster profile
`qlora_task_conditioned_smoke` is allowlisted but **has not been run**.

Do **not** begin T28 until T27C live gates pass.  
Do **not** overwrite T27 job **6059** or T27B job **6382** evidence.

## What was implemented

| Area | Artefact |
|------|----------|
| Field responsibility registry | `configs/model/t27c_field_responsibility_registry_v1.json` |
| Task registry | `configs/model/task_conditioned_prediction_tasks_v1.json` |
| Constrained decoding pin | `configs/model/t27c_constrained_decoding_v1.json` (`lm-format-enforcer==0.10.12`, no fallback) |
| Training config | `configs/model/qlora_task_conditioned_smoke_v1.json` |
| Task contracts | `src/ambiguity_manager/model/task_prediction_contract.py` |
| Constrained decoding | `src/ambiguity_manager/model/task_constrained_decoding.py` |
| Assembler | `src/ambiguity_manager/systems/structured_analysis_assembler.py` |
| Training examples | `src/ambiguity_manager/model/task_conditioned_training.py` |
| Datasets | `src/ambiguity_manager/model/t27c_datasets.py` |
| Orchestrator | `src/ambiguity_manager/model/qlora_task_conditioned_smoke.py` |
| Cluster entry | `scripts/t12_qlora_task_conditioned_smoke.py` |
| Profile | `configs/cluster/t12_job_profiles.json#qlora_task_conditioned_smoke` |

## Datasets (built)

| Set | Count | Notes |
|-----|-------|-------|
| `qlora_task_conditioned_smoke_v1` | 192 source_train / 470 task examples | per-task supervision present |
| `t27c_diagnostic_dev_v1` | 16 source_dev | `diagnostic_only=true`, not final gate |
| `t27c_final_smoke_v1` | 12 source_dev sealed | required-task matrix written |

Historical T27 / T27B validation IDs, holdout, calibration, and model-selection
fixtures are excluded.

## Frozen live thresholds (pre-run)

- task parse ≥ 90%; task schema ≥ 80%
- assembly ≥ 9/12 structural; ≥ 6/12 semantic consistency; ≥ 1/12 full accept
- adapter differs ≥ 1; unsupported commitments 0; unconstrained fallback 0

## Live results

TBD — run:

```text
python scripts/t12_cluster_job.py --run qlora_task_conditioned_smoke --poll --pull
```

## Retained prior evidence

- T27 job 6059 — `configs/model/evidence/t27_task_aligned_qlora_smoke.json`
- T27B job 6382 — `configs/model/evidence/t27b_structured_emission_recovery.json`

## Official identities (unchanged)

- `selected_adapter = null`
- `selected_model_strategy = null`
- `valid_for_official_use = false`
- `t28_may_begin = false` until T27C passes
