# T20 — Context resolver and actual silent-resolution values

**Status:** READY
**foundation_status:** SYNTHETIC_VALIDATION_COMPLETE
**official_execution_status:** BLOCKED

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `10_interpretation_evaluation_framework.md`

## Goal

Resolve ambiguity from supplied evidence and make `silently_resolve` produce an auditable resolved interpretation rather than only a route label.

## Preconditions

- T17 candidate frames exist.
- T19 routing contract exists.

## Required tasks

1. Implement evidence-grounded context resolution across command, scene, dialogue, and capability text.
2. Require selected interpretations to cite supporting evidence and reject conflicting context.
3. Define approved deterministic/frozen policies for fuzzy temporal/quantitative/default resolution.
4. For every silent resolution, emit `resolved_slots`, original values, resolution method, evidence/default policy ID, uncertainty, reversibility, and final selected interpretation.
5. Prevent silent resolution for unsupported, high-risk, unsafe, or capability-incompatible cases.
6. Add tests for correct context resolution, conflicting context, absent context, reversible defaults, and unsafe defaults.
7. Evaluate selected interpretation, context consistency, and resolved-slot correctness on eligible dev records.

## Deliverables

- Context resolver.
- Silent-resolution policy registry.
- Resolved-slot schema/validators.
- Dev outputs/metrics.
- T20 completion report.

## Acceptance criteria

- [ ] Every silent route includes actual resolved values.
- [ ] Resolved values are traceable to gold/evidence or a frozen policy.
- [ ] Conflicting context does not silently win.
- [ ] High-risk/unsupported cases cannot silently resolve.
- [ ] Resolution correctness is measurable.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after context and silent-resolution dev validation. Do not implement external safety or response generation.
