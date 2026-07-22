# ADR: T12 Terminal Zero-Shot Candidate Rejection and Reduced Close-Out Scope

**Status:** Accepted (terminal T12 decision)
**Date:** 2026-07-22
**Ticket:** T12
**Related ADR:** `docs/decisions/ADR_T12_cluster_inference_architecture.md`
**Active execution contract (closing):** `cursor_plan/tickets/T12_cluster_model_stack_setup.md`
**Authoritative final D-Final evidence:** `configs/model/evidence/t12_d_final_live_smoke_final.json`
**Authoritative final D-Final report:** `docs/reports/ticket_T12_D_final_live_smoke_final.md`
**Correction commit:** `f0cf937fef188e9d440bd573a418914889ad9e1a`
**Final live run:** `stage-d-final-live-20260721T105700Z-f0cf937` (Slurm job **3998**)

## Context

T12 forward-migrated to a cluster-native vLLM / Qwen3-8B validation path under
`ADR_T12_cluster_inference_architecture.md`. Stages A–C and the D-path
infrastructure (packaging, transfer, preflight, offline snapshot, pinned SIF,
persistent engine, structured-output transport, response-mode separation, and
evidence retention) were exercised on synthetic fixtures only.

Job **3974** recorded an honest BLOCKED baseline caused by an optional
absent→null round-trip comparison defect (0/4 accepted). Correction `f0cf937`
fixed that comparison path only. The final authorised identical rerun (job
**3998**) accepted **3/4** records; `dfinal-004` failed all three attempts with
`unsupported_silent_commitment` after schema-valid assembly. Schemas, prompts,
fixtures, and attempt budget were not relaxed. The D-Final stop rule therefore
triggered: no further D-Final implementation correction is authorised under T12.

`model_licence_register.selected_model` remains `null`. This record separates an
operational cluster stack from a failed zero-shot candidate-selection gate.

## Decision

### Terminal candidate outcome

1. The **cluster model stack itself is operational** (technical stack evidence
   PASS for packaging, SSH transfer, Slurm scheduling, preflight, offline
   resolution, pinned container, persistent vLLM, structured-output transport,
   strict semantic/safety rejection, and retained negative evidence).
2. **Qwen/Qwen3-8B zero-shot failed** the frozen four-record correctness gate at
   **3/4**, with repeated `unsupported_silent_commitment` on `dfinal-004`.
3. Qwen3-8B is **unsuitable as the zero-shot candidate under the frozen T12
   structured-output and safety contract**. This is **not** a claim that
   Qwen3-8B is universally unsuitable.
4. Terminal model-selection outcome: **`candidate_rejected`**.
5. Candidate selection status: **`NO_SELECTION`**.
6. **`selected_model` remains `null`**. Stage I must not set it for this
   rejected zero-shot strategy.
7. This is a **terminal negative model-selection result**, not a failed cluster
   stack.
8. No further D-Final code, prompt, schema, fixture, or attempt-budget changes
   are authorised under T12.

### Reduced close-out scope (deferred remainder)

| Original stage | Disposition under this ADR |
|---|---|
| **E / E-Minimal** | **Deferred.** Not executed for this rejected candidate. The four-record correctness prerequisite was not met; ten further fixtures would not restore candidate eligibility. Resume only after a viable future model/prompt strategy exists. |
| **F / LoRA feasibility** | **Deferred** to a future model/training strategy ticket. No adapter, optimiser, or training work is required to close T12. |
| **G / performance benchmark** | **Deferred** until a viable candidate is selected. Do not benchmark a candidate rejected on correctness. Retain existing operational timings and hardware facts as historical diagnostics; rely on earlier C-stage resume/conflict evidence rather than repeating it. |
| **H / publication automation** | **Deferred** as non-essential engineering for Honours correctness. No release automation or notifications required to close T12. |
| **I / close-out** | **Execute reduced close-out:** retain runbook and immutable model/container evidence; retain final negative D-Final evidence; add the local Slurm operator and prove it with one lightweight non-model CPU canary; leave `selected_model` null; close T12 with terminal outcome `candidate_rejected`. |

### Authoritative status vocabulary (T12 close-out)

| Field | Value |
|---|---|
| `ticket_status` | `COMPLETE` |
| `technical_stack_status` | `PASS` |
| `candidate_selection_status` | `NO_SELECTION` |
| `terminal_candidate_outcome` | `candidate_rejected` |
| `selected_model` | `null` |
| D-Final correctness gate | `BLOCKED` (3/4; stop rule triggered) |

Do **not** call the candidate correctness gate a PASS. Do **not** claim final
system evaluation is complete.

### Downstream tickets

- **T13** may begin preparation after T12 close (handbook, sampling freeze,
  pilot, annotation tooling). No claim that annotation has started.
- **T14** tooling may be implemented while supervisors are unavailable; human
  annotation and adjudication remain pending.
- Neither T13 nor T14 is marked complete by this ADR.

## Consequences

### Positive

- Honest separation of stack readiness from zero-shot candidate rejection.
- Frozen D-Final contract preserved; safety and schema constraints not weakened
  to force a PASS.
- Clear deferrals avoid spending compute on a rejected candidate (E-Minimal,
  LoRA, perf, publication).
- Reduced Stage I close-out still leaves a reusable Slurm operator + canary for
  later tickets.

### Negative / risks

- No base model is selected; later tickets that assume `selected_model`
  stability remain gated until a future strategy ticket succeeds.
- Readers may misread `ticket_status: COMPLETE` as “model accepted”; the paired
  fields `NO_SELECTION` / `candidate_rejected` / `selected_model: null` are
  mandatory context.

## Explicit non-claims

This ADR does **not** claim:

- that Qwen3-8B is unsuitable for every future prompt, fine-tuning, or contract
  variant;
- that the D-Final four-record correctness gate passed;
- that Stage E, F, G, or H acceptance criteria were satisfied;
- that `selected_model` was set;
- that research-pool or protected data were used;
- that T13/T14 human annotation or adjudication has started;
- that final system evaluation, seven-system comparison, or publication archival
  is complete.

## Linked artefacts

- Architecture ADR: `docs/decisions/ADR_T12_cluster_inference_architecture.md`
- Final D-Final evidence: `configs/model/evidence/t12_d_final_live_smoke_final.json`
- Final D-Final report: `docs/reports/ticket_T12_D_final_live_smoke_final.md`
- Historical job-3974 baseline (preserved): `configs/model/evidence/t12_d_final_live_smoke.json`
- Model licence register: `configs/licences/model_licence_register.json` (`selected_model: null`)
