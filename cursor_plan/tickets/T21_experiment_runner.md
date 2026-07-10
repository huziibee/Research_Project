# T21 — Experiment runner and run matrix

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Build and run the experiment matrix using available splits, baselines, manager variants, and evaluator.

## Required experiments

1. Command-only routing.
2. Scene-context routing.
3. Dialogue-history routing.
4. Safety-sensitive ambiguity.
5. Compound ambiguity.

Only run an experiment if the required dataset/split exists.

## Required tasks

1. Implement experiment config files.
2. Implement runner that records:
   - input split,
   - baseline/model,
   - context mode,
   - output path,
   - timestamp,
   - git commit if available.
3. Run smoke experiments first on tiny samples.
4. Only run full experiments after smoke validation.
5. Save metrics to `outputs/metrics/`.
6. Save predictions to `outputs/predictions/`.
7. Generate `docs/reports/experiment_results.md`.

## Deliverables

- Experiment runner.
- Configs.
- Prediction outputs.
- Metric outputs.
- Results report.
- Completion report.

## Acceptance criteria

- Every metric result references actual gold/prediction files.
- Missing datasets are reported, not faked.
- Results are grouped by dataset/source and baseline.
- No test/gold data was used for prompt/rule tuning during this ticket.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after results report. Do not perform failure analysis yet.

## Experiment protocol requirements

The runner must:

- reject protected-test execution unless a frozen protocol manifest exists;
- save one immutable run directory per system/seed/config;
- record Git/source snapshot, dataset/split/prompt/config/model hashes, model revision, quantisation, decoding settings, seed, hardware, software environment, runtime, token use, invalid outputs, and cost;
- support deterministic primary runs and a predefined repeated-run seed list for stochastic conditions;
- never overwrite prior predictions;
- produce a run manifest that the evaluator and statistics tickets consume.
