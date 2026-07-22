# Adaptation-base selection report

**Date:** 2026-07-22  
**Policy:** `configs/model/adaptation_base_selection_policy_v1.json` (frozen before application)  
**Outcome:** `selected_for_qlora_development`

## Zero-shot vs adaptation-base

| Layer | Value |
|---|---|
| `zero_shot_candidate_status` | `rejected` (immutable) |
| `adaptation_base_status` | `selected_for_qlora_development` |
| `selected_base_model` | `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218` |
| `selected_adapter` | `null` |
| `selected_model_strategy` | `null` |
| `valid_for_official_use` | `false` |

This is **not** an official or final model approval.

## Candidate adaptation-base table

| Candidate | Snapshot | Runtime | Tokenizer | Structured OK | Structured fail notes | Safety severity | Semantic closeness | Attempts | Ctx | BF16 est. | 4-bit QLoRA est. | Training support | Caveats | Eligible | Rank |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen3_8b | verified | vLLM 0.20.1 OK | OK | 3 | 1× unsupported_silent_commitment | medium (1 residual) | high among shortlist | 4 | 40k | ~16 GiB | ~12 GiB | standard HF/PEFT | zero-shot fail retained | **yes** | **1** |
| phi4_14b | verified | vLLM OK | OK | 1 | schema/assembly majority fail | lower residual unsafe | low | 4 | 16k | ~30 GiB | ~16 GiB | standard HF/PEFT | weak structured reliability | yes | 2 |
| mistral_small_24b_2501 | verified snapshot | loads (job 4364) | OK | **0 retained** | evidence-finalisation crash then Apptainer node fail; no accepted package | n/a | n/a | inconclusive | 32k | ~60 GiB | ~20 GiB | plausible | empty/failed retained evidence | **no** (`no_valid_structured_output`) | rejected |

## Ranking rationale

Under the frozen adaptation-base policy (no 4/4 zero-shot requirement):

1. Structured-output reliability: Qwen 3/4 ≫ Phi 1/4 ≫ Mistral 0 retained  
2. Safety severity: Qwen has one residual unsupported commitment (ranked, not hard-rejected for adaptation-base)  
3–9. Remaining criteria preserve Qwen ahead of Phi; Mistral hard-ineligible

## Non-claims

- Does not overturn zero-shot rejection  
- Does not set `selected_adapter` or `selected_model_strategy`  
- Does not approve official use  
- Does not erase Stage-1 failure evidence
