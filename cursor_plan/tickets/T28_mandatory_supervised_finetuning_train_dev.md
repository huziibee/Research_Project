# T28 — Mandatory supervised fine-tuning and dev checkpoint selection

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `04_hardware_model_strategy.md`
- `11_proposal_alignment_contract.md`

## Goal

Train the proposed manager locally and select its final adapter using train/dev only.

## Preconditions

- T27 passed.
- T15 train/dev data is frozen.

## Required tasks

1. Predeclare training runs, stopping rules, checkpoint-selection metric, and maximum resource budget.
2. Train only on train records using the exact T12 base model.
3. Evaluate checkpoints only on dev using T24 metrics and eligibility.
4. Select the final adapter without viewing protected data.
5. Run dev comparisons against the base direct model and provisional prompt-only manager, reporting negative results honestly.
6. Package the adapter, tokenizer/config, load instructions, training data/config hashes, and provenance.
7. Update T23 full and context-blind manager configs to require this adapter.
8. Do not allow a `no_adapter` final proposed-manager decision; inability to produce a valid adapter is BLOCKED.

## Deliverables

- Training runs/logs.
- Dev checkpoint comparison.
- Selected mandatory adapter and hash.
- Updated manager configs.
- T28 completion report.

## Acceptance criteria

- [ ] No protected access occurred.
- [ ] Selection rules were predeclared.
- [ ] The adapter is loadable and schema-valid.
- [ ] The full proposed manager and context-blind manager reference the same selected adapter.
- [ ] Underperformance is retained rather than hidden.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after the final adapter is selected and packaged. Protected evaluation occurs only after T29.
