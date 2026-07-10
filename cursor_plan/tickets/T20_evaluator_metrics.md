# T20 — Evaluator and metrics implementation

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Implement evaluator metrics.

## Metrics

Primary:

- routing correctness

Secondary:

- ambiguity micro-F1,
- ambiguity macro-F1,
- exact ambiguity-set match,
- clarification precision/recall/F1,
- clarification target accuracy,
- intent correctness,
- slot binding correctness,
- risk-sensitive decision accuracy,
- unsafe silent-resolution rate,
- context benefit where paired runs exist.

## Required tasks

1. Implement metric functions.
2. Implement evaluator that takes gold JSONL and prediction JSONL.
3. Validate matching IDs.
4. Report invalid/missing predictions.
5. Generate per-source breakdown.
6. Generate per-route confusion matrix.
7. Generate per-ambiguity-label breakdown.
8. Add unit tests with tiny gold/pred examples.

## Deliverables

- Evaluator module.
- Metric tests.
- CLI/script for evaluation.
- Sample metric output.
- Completion report.

## Acceptance criteria

- Tests cover perfect predictions, partial ambiguity matches, missing predictions, and wrong routes.
- Exact set match differs from multi-label F1.
- Unsafe silent-resolution metric is computed only for safety-relevant/high-risk examples.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after evaluator tests pass. Do not run final experiments.

## Mandatory metric families

Implement all applicable metrics with explicit eligible denominators:

### Routing
- routing accuracy/correctness;
- route macro-F1 and per-route precision/recall/F1;
- route confusion matrix;
- full strategy-sequence exact match and step-level accuracy for `multi_step`.

### Ambiguity
- micro-F1, macro-F1, per-label F1;
- exact ambiguity-set match;
- Hamming loss;
- primary-ambiguity accuracy.

### Risk and capability
- risk accuracy, macro-F1, confusion matrix, high-risk recall, and ordinal error distance;
- capability accuracy, macro-F1, and confusion matrix;
- risk-underestimation and capability-violation rates.

### Clarification and rejection
- clarification precision, recall, F1;
- clarification target accuracy;
- safe rejection rate;
- false rejection rate;
- missed clarification rate;
- unnecessary clarification rate;
- unsafe silent-resolution rate;
- high-risk unsafe-route rate.

### Interpretation and efficiency
- intent correctness and slot/binding correctness where gold exists;
- invalid JSON rate and repair rate;
- latency, token usage, and cost where measurable;
- proportion completed without user interruption.

All metric functions require hand-calculated tiny fixtures and edge-case tests before implementation.
