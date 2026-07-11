# T32 — Statistical uncertainty and paired comparison analysis

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `10_interpretation_evaluation_framework.md`

## Goal

Determine whether system differences are statistically and practically meaningful.

## Preconditions

- T30 official metrics exist.
- T31 cost results exist.

## Required tasks

1. Validate paired record alignment and eligibility for every comparison.
2. Compute frozen bootstrap confidence intervals for primary/supporting metrics.
3. Run paired McNemar tests for binary correctness outcomes where applicable.
4. Run frozen paired bootstrap/permutation tests for F1, cost, and other aggregate differences.
5. Report effect sizes, sample counts, confidence intervals, p-values, and corrected significance.
6. Apply the frozen multiple-comparison correction.
7. Report null/negative findings without selective omission.

## Deliverables

- Statistical scripts/tests.
- CI and paired-test tables.
- Effect-size report.
- T32 completion report.

## Acceptance criteria

- [ ] All comparisons are paired and aligned.
- [ ] Correction is applied as frozen.
- [ ] Sample sizes and effect sizes accompany p-values.
- [ ] No significance claim is made for ineligible or underpowered slices.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after statistical analysis. Do not retune systems.
