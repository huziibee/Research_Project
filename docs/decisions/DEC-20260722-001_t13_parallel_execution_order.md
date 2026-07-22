# Decision Record — T13 parallel execution order

**Decision ID:** `DEC-20260722-001`  
**Date:** `2026-07-22`  
**Status:** accepted  
**Approver:** project author (Mohammed Bangie); supervisors to review at calibration gate  
**Affected tickets:** T13, T14, T15, T16–T24  
**Affected artefacts:** `cursor_plan/tickets/T13_*.md`, `cursor_plan/tickets/T14_*.md`, `cursor_plan/05_master_execution_plan.md`, `cursor_plan/README.md`, `cursor_plan/08_manual_gold_dataset_program.md`

## Summary

T13 proceeds as a human annotation-programme and dataset-preparation ticket without requiring `selected_model`. Local-LLM scenario authoring is optional future tooling. Calibration size is 24; main target is 300. T14A tooling may proceed on synthetic labels while supervisors are unavailable. Model-independent T16–T24 interface and synthetic-fixture work may proceed in parallel. Official training, threshold tuning, and final evaluation remain blocked on adjudicated gold.

## Rationale

T12 closed with `technical_stack_status=PASS`, `terminal_candidate_outcome=candidate_rejected`, and `selected_model=null`. The prior T13 precondition requiring a stable selected model blocked human-gold preparation incorrectly. Human annotation does not depend on a selected inference model. Keeping model-independent engineering idle until gold exists would waste calendar time while supervisors annotate asynchronously.

## Evidence

- `docs/decisions/ADR_T12_terminal_zero_shot_candidate_rejection.md`
- `docs/reports/ticket_T12_completion_report.md`
- `docs/governance/evidence/ETHGOV-001_supervisor_only_determination.md`
- Approved T13 implementation plan (2026-07-22)

## Risk

- Parallel interface work must not claim official metrics or use protected splits.
- Optional LLM authoring must never treat model labels as gold.
- Adjudicator identity remains unresolved until T14 policy approval.

## Required reruns

None. Ticket and roadmap text updates only; no regeneration of T00–T12 artefacts.

## Protected-test implications

None. Protected data remains inaccessible before T29.
