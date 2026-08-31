# T36 — Layered interpretation, classification, and routing failure analysis

**Status:** EARLY_PARTIAL_NON_OFFICIAL — early T36 contains terminal/cost
layers only; T39 extends evidence-only scoring without closing this ticket.

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `10_interpretation_evaluation_framework.md`

## Goal

Explain where errors arise without changing the frozen systems.

## Early-artifact boundary and T39 relationship

The completed `T36_EARLY_LAYERED_FAILURE_ANALYSIS_COMPLETE` artifact is
non-official and covers schema/failure flags, terminal confusion, safety-cost
errors, and predeclared ablations. It does not score intent/CPC/candidate or
wording correctness. T39 may add reproducibility, ambiguity/capability scoring,
structural slices, and a deterministic double-coded route taxonomy from saved
predictions; unavailable interpretation measures remain `NOT_COMPUTED`.

## Preconditions

- T30–T33 outputs exist.
- T34–T35 statuses are recorded.

## Required tasks

1. Create the mandatory interpretation-correct/route-correct four-way cross-tab.
2. Assign a primary failure layer: intent/CPC interpretation, ambiguity classification, risk classification, capability classification, or routing policy.
3. Add detailed interpretation errors: wrong intent/slot, missing/extra candidate, unsupported addition, contradiction, context conflict, invalid output, or wrong silent-resolution value.
4. Add route errors: unnecessary/missed clarification, unsafe execution/resolution, false rejection, capability violation, or wrong multi-step order.
5. Break down by source, ambiguity type/count, risk, capability, route, context mode, critical-slot presence, system, and adapter/architecture condition.
6. Inspect representative cases using saved input, gold, raw output, parsed output, and reason codes under declared sampling rules.
7. Separate evaluator uncertainty/human-review cases from system error.
8. Document negative findings and limitations without post-hoc metric changes.

## Deliverables

- Failure taxonomy and record-level labels.
- Cross-tabs/slice tables.
- Representative casebook.
- Limitations/evaluator-uncertainty report.
- T36 completion report.

## Acceptance criteria

- [ ] Every analysed case is traceable.
- [ ] Risk and capability errors are separated from router errors.
- [ ] Route accuracy is not a proxy for understanding.
- [ ] No cherry-picking or system modification occurs.

## Test and evidence policy

Do not force unit tests for subjective judgement. Test all validators, import/export logic, counters, and deterministic support scripts.

## Stop condition

Stop after failure analysis. Do not rerun tuned variants.
