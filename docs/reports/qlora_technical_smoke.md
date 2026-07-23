# QLoRA technical smoke completion (T27)

Date: 2026-07-23
Author: Mohammed Bangie (2610990)

## Verdict

Live cluster QLoRA technical smoke **PASSED** on the frozen adaptation base.

This does **not** select an adapter, model strategy, or official model.

## Identities (unchanged by smoke)

| Field | Value |
|---|---|
| `zero_shot_candidate_status` | `rejected` (immutable) |
| `adaptation_base_status` | `selected_for_qlora_development` |
| `selected_base_model` | `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218` |
| `selected_adapter` | `null` |
| `selected_model_strategy` | `null` |
| `valid_for_official_use` | `false` |

## Run

| Field | Value |
|---|---|
| Run ID | `t12-qlora-smoke-20260723T064511Z-d6b0182` |
| Slurm job | `6056` |
| Node | `mscluster111` |
| Mode | `real_cluster_training` |
| Operator verify | `VERIFY_PASSED` |
| Runtime | 166.004 s (training loop after load) |
| Wall elapsed | `00:03:25` |
| Peak VRAM | 9822836736 bytes (~9.15 GiB) |
| Frozen params | 4717851648 |
| Trainable adapter params | 7667712 |
| Smoke records | 64 (`source_train` only) |
| Smoke data manifest hash | `70c2efc1cb1f70b59342ceb8369cc492a74664357c782705ac851f919f3ddf23` |
| Resume | `resume_ok=true`, resumed_step=6 then step 7 |
| Base frozen | `base_frozen_verified=true` |
| Adapter vs base text | `base_and_adapter_differ=true` |
| Structured-output smoke | coherent generation retained; JSON object not emitted on the smoke prompt (`collapsed_or_unstructured`) |

## Adapter artefact (not committed)

| Field | Value |
|---|---|
| Path (cluster/local pull) | `adapter/adapter_model.safetensors` |
| Size | 30709192 bytes |
| SHA-256 | `39e7c9a4af2316ee26e19ec764d21e8b577cd19121bdb91dee5beb60bd0a1fab` |
| `technical_smoke_only` | `true` |
| `selected_adapter` | `false` |
| Merged into base | **no** |

## Environment

- Training SIF: `containers/pytorch-2.11.0-cuda13.0-runtime.sif` (pull-based; inference `vllm-openai-v0.20.1.sif` untouched)
- Site packages: `training-site-packages` (peft 0.18.0, bitsandbytes 0.48.1, accelerate 1.11.0, transformers 5.7.0)
- Command: `python scripts/t12_cluster_job.py --run qlora_smoke --poll --pull`

## Compact evidence in-repo

`configs/model/evidence/qlora_smoke_v1/` (manifests/JSON only; large adapter weights excluded).

## Non-claims

- Not full QLoRA training.
- Not an official adapter or model strategy.
- Zero-shot Stage-1 rejection remains recorded.
- Source holdout is not the protected manual challenge set.
