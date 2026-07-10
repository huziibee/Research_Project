# T29 — Statistical uncertainty and paired significance analysis

## Shared context

Project: Risk-Aware Ambiguity Manager. Use only frozen saved predictions from identical examples.

## Goal

Quantify uncertainty and test whether system differences are meaningful.

## Required tasks

1. Compute 95% bootstrap confidence intervals for primary and major safety metrics.
2. Use paired McNemar tests for paired route-correctness comparisons where assumptions hold.
3. Use paired bootstrap or permutation tests for macro-F1 and cost differences.
4. Report effect sizes and sample counts.
5. Apply the predeclared Holm correction for multiple baseline comparisons.
6. Validate assumptions and explicitly mark comparisons that cannot support a test.
7. Save machine-readable results and a human-readable report.

## Deliverables

- statistical test module and tests
- `outputs/statistics/`
- `docs/reports/statistical_analysis.md`
- completion report

## Acceptance criteria

- Paired tests use aligned example IDs.
- Confidence intervals are reproducible with fixed seeds.
- Corrected and uncorrected p-values are both preserved.
- No statistical significance claim is made from unpaired or incompatible data.

## Test-driven development requirements

Use synthetic fixtures with known identical, clearly different, and misaligned prediction cases before implementation.

## Stop condition

Stop after statistical outputs are saved.
