# T31 — Cost-sensitive routing evaluation

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `10_interpretation_evaluation_framework.md`

## Goal

Quantify the unequal consequences of routing and interpretation errors using the frozen cost policy.

## Preconditions

- T30 outputs exist.
- T29 cost matrix is frozen.

## Required tasks

1. Validate the frozen cost matrix and map every scored error to a cost category.
2. Compute total/mean cost overall and by route, risk, ambiguity, and system.
3. Separate interpretation, unsupported-commitment, unsafe action/resolution, false rejection, and interaction costs.
4. Report confidence intervals and paired system cost differences.
5. Run only predeclared sensitivity matrices and label them clearly.
6. Trace every aggregate to record-level cost assignments.

## Deliverables

- Record-level cost outputs.
- Aggregate/slice/sensitivity tables.
- T31 completion report.

## Acceptance criteria

- [ ] No post-hoc cost tuning occurs.
- [ ] Unsafe errors carry their frozen higher penalties.
- [ ] Every cost is traceable.
- [ ] Sensitivity analysis does not replace the primary matrix.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after cost analysis. Do not modify systems or gold.
