# T25 — Human-calibrated semantic verifier

**Status:** STRETCH_NONBLOCKING

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `10_interpretation_evaluation_framework.md`
- `12_core_stretch_policy.md`

## Goal

Optionally build a secondary semantic verifier for paraphrase/free-text edge cases and prove whether it is trustworthy against humans.

## Preconditions

- T14 adjudicated relation subset exists.
- T24 official structured evaluator exists.

## Required tasks

1. Implement normalisation/fuzzy features for dates, numbers, entities, negation, and codes.
2. Add local embedding, reranker, NLI, and optional QA features only when licences/hardware permit.
3. Train/calibrate a small combiner on human-labelled development comparisons.
4. Report macro metrics, confusion, calibration, abstention/risk-coverage, and feature ablations.
5. Predefine thresholds for `official_secondary`, `triage_only`, or `exploratory` status.
6. Record failures, domain slices, and model licences.
7. Do not alter T24 official deterministic scores.

## Deliverables

- Semantic-verifier code/config.
- Human meta-evaluation report.
- Calibration/ablation results.
- Official/triage/exploratory decision.
- T25 completion report.

## Acceptance criteria

- [ ] Human comparison—not intuition—determines status.
- [ ] Contradiction can override similarity.
- [ ] The verifier never creates gold.
- [ ] A truthful `NOT_APPLICABLE` or `BLOCKED_NONCRITICAL` is allowed.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after the verifier status decision. Do not use it on protected outputs before T29 freezes its role.
