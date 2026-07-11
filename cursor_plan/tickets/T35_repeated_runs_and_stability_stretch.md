# T35 — Repeated-run and route-stability analysis

**Status:** STRETCH_NONBLOCKING

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `12_core_stretch_policy.md`

## Goal

Measure stochastic variability and safety-critical route flips under frozen settings.

## Preconditions

- T30 primary predictions exist.
- T29 seed/repetition policy exists if proceeding.

## Required tasks

1. Run the frozen stochastic systems over the predeclared seed set.
2. Confirm deterministic systems remain identical.
3. Compute mean, standard deviation, minimum, maximum, and confidence summaries.
4. Measure per-example interpretation agreement, route agreement, and safety-critical flips.
5. Trace unstable cases to raw outputs and context-sampling features.
6. Do not choose the best seed as the official result.

## Deliverables

- Repeated-run manifests/predictions.
- Stability tables and unstable-case list.
- T35 completion report.

## Acceptance criteria

- [ ] Seeds/settings are frozen.
- [ ] Deterministic drift is treated as a defect.
- [ ] Safety-critical flips are explicit.
- [ ] A truthful nonblocking status is allowed.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after stability analysis. Do not alter decoding or routing.
