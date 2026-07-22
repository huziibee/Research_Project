# T22 — Targeted clarification and face-preserving rejection generation

**Status:** READY
**foundation_status:** SYNTHETIC_VALIDATION_COMPLETE
**official_execution_status:** BLOCKED

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `10_interpretation_evaluation_framework.md`

## Goal

Generate route-appropriate user-facing clarification or rejection outputs from structured missing information and constraints.

## Preconditions

- T19 routes exist.
- T20 unresolved/resolved slots exist.
- T21 safety reasons are available.

## Required tasks

1. Implement deterministic/template-first targeted clarification from unresolved critical slots, candidate distinctions, safety prerequisites, and capability uncertainty.
2. Implement face-preserving rejection messages that state the relevant safety/capability constraint without fabricating policy.
3. Support ordered multi-step response plans.
4. Emit structured clarification targets and rejection reason codes separately from surface wording.
5. Add tests for object, destination, time, quantity, safety, capability, compound, and no-question cases.
6. Evaluate clarification-target and rejection-reason correctness on eligible dev records.
7. Keep free-text quality secondary to structured functional correctness.

## Deliverables

- Clarification/rejection generators.
- Structured target/reason schemas.
- Template tests and dev metrics.
- T22 completion report.

## Acceptance criteria

- [ ] Questions target the actual unresolved fields.
- [ ] Rejections correspond to verified risk/capability reasons.
- [ ] No generic clarification is used when a targeted question is possible.
- [ ] Surface text does not determine official correctness.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after response generation passes dev evaluation. Do not integrate all systems yet.
