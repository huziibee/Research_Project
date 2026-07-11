# T26 — Immutable experiment runner implementation

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `03_dataset_roles_metrics.md`
- `10_interpretation_evaluation_framework.md`

## Goal

Build the runner that will later execute frozen systems, while proving provenance and eligibility without running protected final experiments.

## Preconditions

- T23 systems exist.
- T24 evaluator passes.
- T25 status is recorded or not applicable.

## Required tasks

1. Implement config-driven system/dataset/split/seed matrix execution.
2. Enforce T15 eligibility and record skipped/ineligible/error reasons.
3. Preserve input, raw output, parsed output, validation, timing, token, and error records.
4. Create immutable run IDs, manifests, hashes, resumability, and non-overwrite behaviour.
5. Add model/runtime health checks and bounded retry policy.
6. Integrate T24 scoring and optional T25 secondary scoring according to status.
7. Implement a protected-mode guard that remains disabled until a valid T29 protocol manifest exists.
8. Run only fixtures/train/dev dry runs and verify row accounting.

## Deliverables

- Experiment runner.
- Run-manifest schema.
- Resume/non-overwrite/protected-guard tests.
- Dry-run artifacts.
- T26 completion report.

## Acceptance criteria

- [ ] Protected mode cannot run without T29.
- [ ] Every input ends as prediction, ineligible, or explicit failure.
- [ ] No output is overwritten.
- [ ] Scores reference exact gold/prediction/eligibility versions.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after dry-run validation. Do not perform mandatory training or protected execution.
