# T19 — Ambiguity/risk/capability classification and deterministic routing

**Status:** READY
**foundation_status:** SYNTHETIC_VALIDATION_COMPLETE
**official_execution_status:** BLOCKED

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `11_proposal_alignment_contract.md`
- `10_interpretation_evaluation_framework.md`

## Goal

Build the type-and-risk-aware decision layer that consumes structured model signals and issues the final route.

## Preconditions

- T17 candidate generator exists.
- T18 uncertainty feature exists.

## Required tasks

1. Implement/prompt the structured ambiguity, risk, and capability classifier using schema-v2 labels.
2. Define deterministic route precedence and tie-breaking rules before dev tuning.
3. Require clear, safe, capable, supported commands to execute.
4. Permit silent resolution only for low/none-risk resolvable fuzzy parameters with an approved policy and sufficient confidence.
5. Require clarification/multi-step for unresolved critical information, especially under high risk.
6. Use face-preserving rejection for known unsafe/prohibited or incapable requests; if ambiguity prevents the safety/capability determination, clarify or multi-step first.
7. Generate ordered strategy sequences for dependent compound ambiguities.
8. Use context-sampling uncertainty as an explicit escalation feature.
9. Add exhaustive table-driven tests for route precedence, conflicts, and invariants.
10. Run dev-only route/classification metrics and error traces.

## Deliverables

- Classifier configs/outputs.
- Deterministic router and precedence specification.
- Route-table tests.
- Dev metrics and T19 completion report.

## Acceptance criteria

- [ ] Final route is reproducible from saved structured signals/config.
- [ ] Safety/capability conflict rules are explicit.
- [ ] Silent resolution is impossible without T20-resolvable fields.
- [ ] Multi-step order is validated.
- [ ] No protected data is used.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after classifier/router dev validation. Do not implement context resolution or response text.
