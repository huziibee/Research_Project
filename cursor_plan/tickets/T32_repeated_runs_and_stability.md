# T32 — Repeated runs and prediction stability

## Shared context

Project: Risk-Aware Ambiguity Manager. Follow the predefined seed list in the frozen protocol.

## Goal

Measure stochastic variability and routing stability.

## Required tasks

1. Run deterministic primary conditions once where temperature-zero determinism is supported.
2. Run stochastic conditions over the predefined seed list, normally at least 3–5 seeds.
3. Report mean, standard deviation, minimum, and maximum for primary metrics.
4. Compute per-example prediction agreement/stability across runs.
5. Identify safety-critical flip cases.
6. Save all run manifests and aggregate results.

## Deliverables

- repeated-run configs
- stability evaluator and tests
- aggregate outputs
- stability report
- completion report

## Acceptance criteria

- Every run uses the same frozen examples.
- Seeds and decoding settings are recorded.
- Safety-critical instability is separately reported.

## Test-driven development requirements

Use synthetic repeated-prediction fixtures to verify aggregation and flip detection.

## Stop condition

Stop after stability results are saved.
