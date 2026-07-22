# Decision Record — Development on source data with delayed manual protected challenge evaluation

**Decision ID:** `DEC-20260722-002`  
**Date:** `2026-07-22`  
**Status:** accepted  
**Approver:** project author (Mohammed Bangie); supervisors to review  
**Affected tickets:** T13, T14, T15, T16–T30  
**Affected artefacts:** `cursor_plan/03_dataset_roles_metrics.md`, `cursor_plan/05_master_execution_plan.md`, `cursor_plan/README.md`, `cursor_plan/08_manual_gold_dataset_program.md`, `configs/manager/system_variants_v1.json`

## Summary

Model development, selection, training, prompt work, threshold tuning, and ablations may proceed on existing source datasets and synthetic fixtures while the future supervisor-double-annotated manual gold remains unavailable. The 24 T13 calibration records are annotation-process material only. The future approximately 300-record adjudicated set is designated `manual_protected_challenge_set` and must not influence development. All model, adapter, prompt, policy, metric, threshold, and statistical choices must be frozen at T29 before that manual gold is unlocked for final protected execution. Variant-aware analysis caching is required so `full_context` and `context_blind` analyses can coexist per record without cross-variant leakage.

## Rationale

T12 closed with `selected_model=null` and a rejected zero-shot candidate, but calendar time should not idle while supervisors annotate asynchronously. Source datasets already carry verified labels for many metric families; synthetic fixtures support interface and evaluator development without inventing gold. Using T13 calibration or peeking at future manual gold during development would contaminate protected evaluation. Separating development partitions from the delayed manual challenge set preserves the integrity of T30 official results while allowing parallel engineering.

## Development data

Existing source datasets and synthetic fixtures may be used for:

- base-model selection;
- provider development;
- QLoRA training;
- adapter selection;
- prompt development;
- uncertainty and routing threshold development;
- development experiments and ablations.

Each record used in development scoring or selection must have explicit metric eligibility under the T15 manifest rules. Weak or unavailable labels must not be invented; missing gold stays `null` and excludes the record from that metric.

## Manual data — future `manual_protected_challenge_set`

The future approximately 300-record supervisor-double-annotated dataset (T14B annotation, T14C adjudication, T15 protected split) is intended to serve as **`manual_protected_challenge_set`**. It does **not** exist yet and must not be marked as existing.

It must not be used for:

- model selection;
- training;
- adapter selection;
- prompt editing;
- threshold tuning;
- policy editing;
- development error correction.

## Current calibration package

The 24 T13 calibration records remain **annotation-process calibration material** (handbook refinement, interface rehearsal, annotator alignment). They must not enter:

- the model bake-off;
- training;
- source development sets;
- synthetic evaluator fixtures;
- protected model evaluation.

## Protocol freeze

The model, adapter, prompts, policies, metrics, thresholds, and statistical plan must be frozen at **T29** before the future manual gold is unlocked for final execution at **T30**. No development feedback from the protected challenge set may revise frozen artefacts.

## Variant-aware analysis cache

Development and official execution require variant-aware analysis caching so `full_context` and `context_blind` analyses can coexist per record. A system requiring `context_blind` must not reuse a `full_context` cache entry; cache identity must include the analysis variant and ablated-input hash where applicable.

## Evidence

- `docs/decisions/DEC-20260722-001_t13_parallel_execution_order.md`
- `docs/decisions/ADR_T12_terminal_zero_shot_candidate_rejection.md`
- `docs/reports/ticket_T13_foundation_and_calibration.md`
- `docs/reports/ticket_T16_T24_model_independent_foundation.md`
- `docs/reports/ticket_T16_T24_context_ablation_and_run_status_fix.md`
- `cursor_plan/08_manual_gold_dataset_program.md`

## Risk

- Source-development tuning may overfit development partitions; T29 freeze and T15 group-safe splits limit but do not eliminate this risk before protected execution.
- Parallel work must not treat T13 calibration labels as development gold or bake-off evidence.
- Engineers must not pre-access or simulate future manual gold for threshold or prompt iteration.
- Shared analysis caches without variant separation would leak scene context into the context-blind ablation.

## Required reruns

None. Documentation and governance-log updates only; no regeneration of completed T00–T16 artefacts.

## Protected-test implications

The future `manual_protected_challenge_set` remains inaccessible until T29 protocol freeze and T30 authorised execution. Development on source data and synthetic fixtures does not constitute protected-test access. T13 calibration records are excluded from protected evaluation.
