# T17 — Structured candidate-interpretation generator

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `10_interpretation_evaluation_framework.md`

## Goal

Generate evidence-grounded candidate meanings without making the final route decision.

## Preconditions

- T16 proves the base model and parser.

## Required tasks

1. Implement schema-v2 candidate frames containing intent/speech act, CPC slots, evidence, confidence, and unresolved fields.
2. Require zero/one/many candidates as appropriate and forbid selecting one without unique evidence.
3. Canonicalise aliases, units, dates, quantities, and identifiers through deterministic helpers.
4. Reject or flag unsupported details, context contradictions, and duplicate candidates.
5. Implement candidate ranking only as a non-final signal for later components.
6. Run train/dev fixtures for clear, ambiguous, compound, context-resolved, and insufficient-information cases.
7. Measure candidate precision/recall on eligible dev data without touching protected data.

## Deliverables

- Candidate generator and schemas.
- Canonicalisation/evidence validators.
- Dev outputs and metrics.
- T17 completion report.

## Acceptance criteria

- [ ] Candidate output is structured, not free-form only.
- [ ] Evidence references real input content.
- [ ] No route decision is made.
- [ ] Multiple valid meanings are preserved.
- [ ] Unsupported commitment is prevented or explicitly flagged.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after candidate generation passes dev fixtures. Do not implement uncertainty or routing.
