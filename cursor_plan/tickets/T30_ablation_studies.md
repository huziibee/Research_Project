# T30 — Ablation studies

## Shared context

Project: Risk-Aware Ambiguity Manager. Follow the frozen experiment protocol.

## Goal

Identify which components of the proposed manager contribute to performance.

## Mandatory ablations

- full manager without risk signal;
- without capability signal;
- without ambiguity-type signal;
- without context;
- without uncertainty/context-sampling feature if implemented;
- without multi-step routing;
- direct generation without structured routing where feasible.

## Required tasks

1. Implement ablations through configuration, not duplicated code.
2. Verify exactly one intended component is removed per condition.
3. Run on identical frozen examples and seeds.
4. Evaluate routing, safety, risk/capability, cost, and compound metrics.
5. Save predictions, metrics, and comparison table.

## Deliverables

- ablation configs
- invariant tests
- `outputs/ablations/`
- `docs/reports/ablation_results.md`
- completion report

## Acceptance criteria

- Ablations are reproducible and differ only as declared.
- Full-system outputs are not overwritten.
- Negative ablation findings are retained.

## Test-driven development requirements

Write configuration/invariant tests proving each ablation disables only its named component.

## Stop condition

Stop after all predeclared ablations are evaluated.
