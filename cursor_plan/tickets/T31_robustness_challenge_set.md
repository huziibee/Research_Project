# T31 — Robustness and challenge-set evaluation

## Shared context

Project: Risk-Aware Ambiguity Manager. The challenge set is separate from normal train/dev/test and must not be used for tuning.

## Goal

Measure degradation under realistic perturbations and unseen compound cases.

## Required challenge categories

- paraphrases;
- spelling/grammar noise;
- reordered clauses;
- irrelevant context;
- contradictory context;
- missing context;
- longer compound commands;
- unseen ambiguity combinations;
- changed capability descriptions;
- adversarial/borderline phrasing;
- optional SafeAgentBench rejection stress slice if verified.

## Required tasks

1. Define deterministic transformation rules where possible.
2. Preserve source IDs and link each challenge example to its base example.
3. Manually review transformations for semantic-label preservation.
4. Keep challenge examples outside tuning.
5. Measure absolute performance and degradation from matched clean examples.
6. Save per-category results and examples.

## Deliverables

- challenge manifest
- transformation scripts and tests
- reviewed challenge set
- `outputs/robustness/`
- robustness report
- completion report

## Acceptance criteria

- No challenge example leaks into training/dev.
- Label-preservation review is recorded.
- Degradation is reported by challenge category.

## Test-driven development requirements

Test deterministic transforms, ID linkage, split exclusion, and unchanged labels for controlled fixtures.

## Stop condition

Stop after robustness results are saved.
