# T12 Stage D-Final — Final Live Structured Generation Smoke (BLOCKED)

**Ticket:** T12
**Stage:** D-Final final authorised live rerun
**Measurement timestamp:** 2026-07-21T13:09:10Z
**Correction commit:** `f0cf937fef188e9d440bd573a418914889ad9e1a`
**Status:** BLOCKED — 3/4 accepted; stop rule triggered

## 1. Relationship to job 3974

Job **3974** remains the authoritative historical BLOCKED baseline:

- evidence: `configs/model/evidence/t12_d_final_live_smoke.json`
- report: `docs/reports/ticket_T12_D_final_live_smoke.md`
- failure: optional absent→null round-trip comparison defect (0/4 accepted)

That package was **not** overwritten.

## 2. Correction

`fix(t12): normalize optional nulls in semantic round trip` applied comparison-only
path-aware materialisation for:

- `candidate_interpretations[*].text`
- `candidate_interpretations[*].safety_status`
- `supporting_evidence[*].note` / `selected_interpretation.supporting_evidence[*].note`

Empty `supporting_evidence` remains schema-invalid. No schema, prompt, fixture, or
attempt-budget change.

## 3. Source transfer

| Field | Value |
|---|---|
| Commit | `f0cf937fef188e9d440bd573a418914889ad9e1a` |
| Archive | `t12-f0cf937.tar.gz` |
| Archive SHA-256 | `32990cf09565a7722401c205fd05259606bdd81cb6ae220eaa086525dff6b383` |
| Archive bytes | 228517142 |
| Transfer | `git_archive` |

## 4. Run identity (job 3998)

| Field | Value |
|---|---|
| Run ID | `stage-d-final-live-20260721T105700Z-f0cf937` |
| Prep | `${T12_CLUSTER_ROOT}/runs/stage-d-final/.prep-stage-d-final-live-20260721T105700Z-f0cf937` |
| Run dir | `${T12_CLUSTER_ROOT}/runs/stage-d-final/stage-d-final-live-20260721T105700Z-f0cf937` |
| Slurm job | 3998 |
| Node | `mscluster112` (allowlist 110/111/112; exclusive `biggpu`) |
| GPU | NVIDIA RTX PRO 6000 Blackwell Workstation Edition |
| VRAM | 97887 MiB |
| Compute capability | 12.0 |
| Driver | 595.71.05 |
| Slurm log | `${T12_CLUSTER_ROOT}/logs/t12-d-final-live-3998.out` |

## 5. Gates passed

| Gate | Result |
|---|---|
| Archive verification | pass |
| Full SIF SHA-256 | pass (`d404bdf4…`, 14.223 s) |
| Nested preflight | pass |
| Offline / snapshot | pass (`network_fallback=false`) |
| Structured-output construction | `constructed` |
| Engine start | 1 |
| Response-mode selection | `enable_thinking_false` (`verified_for_run`) |
| Round-trip optional-null defect | resolved on this rerun |

### Generation-call accounting

| Count | Value |
|---|---|
| probe | 2 |
| record | 9 |
| total | 11 |
| runner-reported (probe-only) | 2 |

## 6. Four-record outcome

| Record | Attempts | Final | Notes |
|---|---|---|---|
| `dfinal-001` | 1 | **accepted** | execute path |
| `dfinal-002` | 3 | **accepted** | empty SE ×2 then accepted |
| `dfinal-003` | 2 | **accepted** | empty SE ×1 then accepted |
| `dfinal-004` | 3 | rejected_after_attempts | unsupported_silent_commitment ×3 (schema+assembly OK) |

Totals: accepted **3**; rejected_after_attempts **1**; strict semantic-schema-valid accepted **3**;
canonical schema-v2-valid accepted **3**; unsupported commitments on accepted **0**;
raw attempts retained **9**; semantic correctness `not_evaluated`.

## 7. Stop rule

Final authorised D-Final correction + one identical rerun did **not** achieve 4/4.

Therefore:

- no further D-Final implementation correction is permitted;
- schemas, prompts, fixtures, and attempt budget must not be relaxed for another try;
- Qwen3-8B zero-shot under the frozen contract is classified **unsuitable**;
- next step is a formal model/prompt strategy decision.

## 8. Non-claims

- No four-record D-Final PASS
- Stage D not complete
- `selected_model` remains null
- No T13/T14 annotation, training, or LoRA
