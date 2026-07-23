# ADR: Task-Conditioned Partial-Schema Prediction with Deterministic StructuredAnalysis Assembly

**Decision ID:** `ADR-T27C-001`
**Date:** 2026-07-23
**Status:** accepted
**Ticket:** T27C
**Author:** Mohammed Bangie — 2610990
**Approver:** project owner (development freeze for technical smoke)
**Related evidence (immutable, retained):**
- T27 job **6059** — `configs/model/evidence/t27_task_aligned_qlora_smoke.json`
  (`t12-qlora-task-aligned-20260723T074715Z-991732e`)
- T27B job **6382** — `configs/model/evidence/t27b_structured_emission_recovery.json`
  (`t12-qlora-emission-recovery-20260723T090929Z-3ae20c7`; evidence commit
  `b8891d50c51ccb304381e5bf83aa64841d99fefa`)

## Context

Two controlled attempts required the model to emit the full production semantic
envelope in one generation call:

1. **T27 (job 6059):** task-aligned partial training targets (~6.79% supervised
   tokens) vs full 25-field inference schema → **0/4 accepted**.
2. **T27B (job 6382):** full-schema envelope training with structural+semantic
   supervision (~34.01% supervised tokens) → mechanics PASS, but **0/8 accepted**.
   Failures included truncation, no JSON, parse failure, and unknown fields.

Increasing structural supervision did not produce reliable full-envelope output.
The full envelope contains many fields that are weakly supervised, unsupported,
or already owned by deterministic components (router, classification aggregate,
context/uncertainty, safety, provenance).

## Decision

Adopt **task-conditioned partial-schema prediction** plus **deterministic
StructuredAnalysis assembly** for the T27C technical smoke:

1. Train one **shared** adapter on small, stable **task-specific JSON schemas**.
2. Create a training example **only when** the source record supports that task.
3. At inference, run several narrowly scoped prediction tasks.
4. Validate every partial result independently.
5. Combine valid partial results through deterministic assembler code.
6. Derive routing and related decisions **outside** the LLM.
7. Never require the model to emit the entire production StructuredAnalysis
   object in one call.

### Explicit non-claims

- This is **not** a prompt-only repair of T27/T27B.
- T27 and T27B evidence remains **valid blocked structured-output evidence** and
  must not be overwritten, removed, weakened, or reinterpreted.
- Task-conditioned outputs are **intermediate predictions**, not final system
  results.
- T27C uses **one shared adapter**; no task-specific adapter search is permitted.
- The T27C smoke adapter must not become `selected_adapter`.
- `selected_model_strategy` remains null; `valid_for_official_use` remains false.
- The immutable base
  `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218` is unchanged.
- **T28 remains blocked until T27C passes.**

### Artefacts

| Artefact | Path |
|---|---|
| Field responsibility registry | `configs/model/t27c_field_responsibility_registry_v1.json` |
| Task registry | `configs/model/task_conditioned_prediction_tasks_v1.json` |
| Training config | `configs/model/qlora_task_conditioned_smoke_v1.json` |
| Assembler | `src/ambiguity_manager/systems/structured_analysis_assembler.py` |
| Task prediction contracts | `src/ambiguity_manager/model/task_prediction_contract.py` |

## Rationale

- One-call full-schema generation failed twice under real cluster conditions.
- Full-envelope targets mix unsupported, deterministic, and model-owned fields.
- Partial source labels map naturally onto separate eligibility tasks already
  present in `training_target_policy_v1.json`.
- Smaller schemas reduce generation length and structural complexity.
- Deterministic assembly preserves safety, provenance, and fail-safe routing.
- The production router (`DeterministicRouter`) must remain authoritative.

## Evidence

- `docs/reports/ticket_T27_task_aligned_qlora_smoke.md`
- `docs/reports/ticket_T27B_target_schema_compatibility_audit.md`
- `docs/reports/ticket_T27B_structured_emission_recovery.md`
- `configs/model/t27b_production_schema_coverage_v1.json`

## Risk

- Task decomposition may omit a field the evaluator expects if assembly policy
  is incomplete → mitigate with registry tests and full production schema
  validation after assembly.
- Constrained decoding may be unavailable in the training SIF → fail the task
  call explicitly; no unconstrained fallback is permitted in the live profile.
- Shared-adapter interference across tasks → acceptable for T27C technical
  smoke only; task-specific adapters are out of scope.

## Required reruns

One controlled live profile: `qlora_task_conditioned_smoke`.
One technical-defect rerun is permitted under the T27C one-rerun policy.

## Protected-test implications

No source_holdout, T13 calibration, supervisor annotations, future manual
challenge, model-selection fixtures, or historical T27/T27B validation IDs may
enter training, diagnostic, or sealed sets. Official selection identities remain
null.
