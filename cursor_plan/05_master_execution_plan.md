# 05 — Master Execution Plan for Cursor

This plan is stage-gated, token-efficient, and experiment-complete. Use one ticket per fresh Cursor context.

## Core operating rules

- Always attach `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the current ticket.
- Cursor must inspect actual repository artifacts, propose a short plan, implement only the ticket, run ticket-level validation, create the completion report, and stop.
- TDD is mandatory for deterministic behavior named in the global contract.
- Human approval is required between tickets.

## Phases and gates

### Phase 0 — Foundation

`T00–T02`

Gate: scaffold, schema direction, actual data inventory, licence/inclusion register.

### Phase 1 — Dataset conversion and weak pool

`T03–T09`

Gate: validated converters, complete row accounting, provenance, weak/gold separation.

### Phase 2 — Manual gold data, agreement, and splits

`T10–T12`

Gate: manual compound dataset and guidelines, double annotation and agreement, adjudication, group-aware frozen splits, leakage checks.

### Phase 3 — Systems and required baselines

`T13–T19`

Gate: structured direct LLM, candidate generator, full manager, context/safety/clarification behavior, always-execute/clarify/resolve, degree-based routing, context-blind ablation.

### Phase 4 — Metrics, runner, and local-model option

`T20–T24`

Gate: complete metric suite, immutable run manifests, local inference if used, optional fine-tuning condition clearly separated from the guaranteed prompted manager.

### Phase 5 — Freeze and execute the complete experiment

`T27` then `T21/T24` as applicable, followed by `T28–T32`

Gate: frozen protocol before protected test access; cost-sensitive evaluation; statistical uncertainty; ablations; robustness; repeated-run stability.

### Phase 6 — Analysis and evidence package

`T25`, `T26`, `T33`

Gate: failure analysis, all final tables/artifacts, reproducibility documents, and a final readiness PASS.

## Recommended exact order

```text
T00 T01 T02
T03 T04 T05 T06 T07 T08 T09
T10 T11 T12
T13 T14 T15 T16 T17 T18 T19 T20
T22
T23 and T24 only if approved
T27
T21 final frozen runs
T28 T29 T30 T31 T32
T25 T26 T33
```

`T21` may be implemented earlier, but final protected-test runs occur only after `T27` passes.

## Do not continue when

- any stage gate fails;
- a required label mapping or licence is unverified;
- the test set has been accessed before protocol freeze;
- exact or near-duplicate leakage remains;
- required degree-based routing is absent;
- metrics do not cover risk, capability, rejection, and compound routing;
- outputs lack manifests/hashes;
- Cursor weakened tests or guessed labels;
- the human has not approved the completion report.

## Human review checklist

```text
[ ] Scope stayed inside the ticket.
[ ] TDD was used where required and the initial failure is recorded.
[ ] No fake fields, labels, rows, citations, or results.
[ ] Validation commands actually ran.
[ ] Outputs are versioned and traceable.
[ ] Protected-test rules were respected.
[ ] TODO/BLOCKED items are resolved or intentionally deferred.
[ ] Completion report exists and stage gate is honest.
```
