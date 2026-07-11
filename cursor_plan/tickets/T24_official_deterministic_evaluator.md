# T24 — Official deterministic interpretation and routing evaluator

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `10_interpretation_evaluation_framework.md`
- `03_dataset_roles_metrics.md`

## Goal

Build the official non-LLM scoring system with hand-verifiable formulas and machine-enforced eligibility.

## Preconditions

- T15 eligibility manifest exists.
- T23 canonical prediction schema exists.

## Required tasks

1. Implement alignment by record ID with duplicate/missing/mismatch guards.
2. Implement intent accuracy; CPC slot precision/recall/F1; critical-slot correctness; and CPC exact match.
3. Implement one-to-one candidate-set matching, selected-interpretation accuracy, unresolved-slot F1, unsupported commitment, hallucinated detail, and context contradiction.
4. Implement ambiguity micro/macro F1 and exact ambiguity-set match.
5. Implement risk accuracy/macro-F1/ordinal error/underestimation and capability accuracy/violation.
6. Implement routing correctness, route macro-F1/per-route metrics, confusion matrix, and multi-step exact sequence.
7. Implement clarification precision/recall/F1 and target correctness; safe rejection and rejection-reason correctness; unsafe silent-resolution rate and resolved-slot value correctness.
8. Implement invalid JSON/repair, latency, token, and compute summaries.
9. Consume the T15 eligibility manifest and report eligible N plus exclusion reasons for every metric.
10. Create hand-calculated fixtures for every formula and failure mode.

## Deliverables

- Evaluator package.
- Metric specification/formulas.
- Hand-calculated fixtures/tests.
- Eligibility/exclusion reports.
- T24 completion report.

## Acceptance criteria

- [ ] No generative model judges official correctness.
- [ ] Every formula passes known-answer tests.
- [ ] Missing gold is excluded.
- [ ] Interpretation and route are separate.
- [ ] Silent-resolution values are scored.
- [ ] Every metric reports denominator and sources.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after evaluator fixtures pass. Do not run protected predictions.
