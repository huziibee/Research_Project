# T30 — Final frozen seven-system experiment execution

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `03_dataset_roles_metrics.md`
- `10_interpretation_evaluation_framework.md`

## Goal

Run all seven mandatory frozen systems on every eligible protected record and gather complete official results.

## Preconditions

- T29 protocol/guard passed.
- Protected access approval is recorded.

## Required tasks

1. Verify all hashes and environment/model/adapter availability before each run.
2. Run `always_execute`, `always_clarify`, `always_silently_resolve`, `direct_base_llm`, `degree_based_router`, `context_blind_manager`, and `full_finetuned_type_risk_manager`.
3. Run only eligible dataset/metric conditions from the frozen manifest.
4. Save every input, raw model response, parsed prediction, validation/repair, timing, token, error, and manifest record.
5. Resume failures only under the frozen retry policy.
6. Calculate T24 official metrics and approved T25 secondary metrics without changing thresholds.
7. Produce per-system, per-source, per-ambiguity, per-risk, compound-status, and context-mode tables with eligible N.
8. Generate the interpretation-vs-route four-way cross-tab.
9. Reconcile expected versus completed run matrix and fail on any missing mandatory condition.

## Deliverables

- Immutable protected predictions.
- Run manifests/access logs.
- Official metric files and cross-tabs.
- Run-matrix reconciliation.
- T30 completion report.

## Acceptance criteria

- [ ] All seven mandatory systems completed or the ticket is not PASS.
- [ ] No configuration changed after freeze.
- [ ] Every metric traces to aligned gold/predictions.
- [ ] All failures/skips are explicit.
- [ ] Interpretation and route results are separate.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after the complete protected matrix and official metrics are saved. Do not tune or redesign any system.
