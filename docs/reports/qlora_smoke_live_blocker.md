# QLoRA technical smoke — live execution blocker

Date: 2026-07-22  
Ticket: T27  
Author: Mohammed Bangie (2610990)

## Verdict

Adaptation-base selection and the QLoRA smoke **pipeline** are complete. The **live** cluster smoke is blocked by an unreachable post-auth SSH session on `wits-mscluster` (`146.141.21.100`).

## What is ready

- `selected_base_model = Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`
- `adaptation_base_status = selected_for_qlora_development`
- `zero_shot_candidate_status = rejected` (immutable)
- `selected_adapter = null`
- `selected_model_strategy = null`
- `valid_for_official_use = false`
- Source splits frozen under `data/development/source_splits_v1/`
- Smoke data frozen under `data/development/qlora_smoke_v1/` (64 records)
- Operator profile `qlora_smoke` uses pull-based training runtime:
  - SIF: `containers/pytorch-2.11.0-cuda13.0-runtime.sif`
  - site-packages: `training-site-packages`
- Local mock/unit suite `tests/test_t27_qlora_smoke.py` passes

## Cluster progress already achieved (before hang)

| Job | Outcome |
|-----|---------|
| 4544 / 4576 | Apptainer `%post` build failed (no usable subuid/fakeroot) |
| 4595 | COMPLETED: pulled pytorch runtime SIF; pip-installed peft/bitsandbytes/accelerate/transformers into `~/t12-hpc/training-site-packages` |

## Remaining live steps (blocked on SSH)

1. Remove shadowed `torch` / `triton` / `nvidia_*` wheels from `~/t12-hpc/training-site-packages` so the container torch is used.
2. Record SIF SHA-256 and size into the training environment evidence.
3. Run: `python scripts/t12_cluster_job.py --run qlora_smoke --poll --pull`
4. Commit compact smoke evidence only (`evidence(t27): record QLoRA technical smoke`).

## SSH failure signature

- TCP port 22 reachable
- Public-key authentication succeeds
- Session then stalls after `Entering interactive session` with:
  `Timeout, server 146.141.21.100 not responding.`
- Observed repeatedly with `BatchMode`, `RequestTTY=no`, and direct `/bin/echo`

This matches a hung login-node / NFS home session rather than a repository defect.

## Stop-condition mapping

Stop condition triggered: **smoke evidence cannot be finalised** (cluster session unavailable).

Not triggered: repository state unsafe; adaptation-base hard-requirement failure; source leakage; selected base missing.
