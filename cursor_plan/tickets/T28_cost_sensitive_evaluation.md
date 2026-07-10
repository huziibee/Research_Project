# T28 — Cost-sensitive and safety-weighted evaluation

## Shared context

Project: Risk-Aware Ambiguity Manager. Follow the global contract and frozen experiment protocol.

## Goal

Evaluate errors according to consequence, not only equal-weight accuracy.

## Required tasks

1. Define and justify a route-error cost matrix before protected-test results are inspected.
2. Version and hash the matrix.
3. Implement:
   - mean and total safety-weighted cost;
   - cost by risk level;
   - cost by ambiguity type;
   - cost by route;
   - high-risk false-negative/unsafe-route cost;
   - bootstrap confidence intervals for cost differences.
4. Add sensitivity analysis using at least two plausible alternative matrices without changing the ranking claim opportunistically.
5. Save machine-readable outputs and a report.

## Deliverables

- cost matrix config
- cost evaluator and tests
- `outputs/cost_sensitive/`
- report
- completion report

## Acceptance criteria

- Every matrix entry is explicit.
- Results are derived from saved gold/prediction files.
- Sensitivity analysis is reported honestly.

## Test-driven development requirements

Use hand-calculated fixtures covering all route-pair costs, missing labels, and denominator edge cases.

## Stop condition

Stop after cost-sensitive outputs are saved.
