# T25 — Failure analysis

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Perform structured failure analysis on experiment outputs.

## Required breakdowns

Analyze errors by:

- source dataset,
- ambiguity type,
- route label,
- compound vs non-compound,
- risk/safety-precondition status,
- context mode,
- baseline/model.

## Error categories

Use at least:

- wrong route,
- missed ambiguity,
- extra ambiguity label,
- wrong primary ambiguity,
- wrong missing slot,
- poor clarification target,
- over-clarification,
- unsafe silent resolution,
- context ignored,
- safety-loop error,
- invalid JSON/output.

## Required tasks

1. Load gold, predictions, and metric outputs.
2. Generate failure tables.
3. Sample representative examples per failure category.
4. Create confusion matrices/plots if useful.
5. Write `docs/reports/failure_analysis.md`.

## Deliverables

- Failure analysis report.
- Error slice CSV/JSON files.
- Optional plots/tables.
- Completion report.

## Acceptance criteria

- Failure examples reference actual IDs and source datasets.
- No fabricated examples.
- Report distinguishes classifier errors from router errors.
- Safety-sensitive failures are highlighted.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after failure report. Do not write final paper artifacts.

## Expanded failure analysis

Also separate:

- risk underestimation vs overestimation;
- capability misclassification;
- incorrect multi-step ordering;
- hallucinated context;
- malformed/repair-failed outputs;
- model instability across repeated runs;
- errors unique to each baseline and ablation.

Use a predeclared sampling procedure for qualitative examples so only convenient failures are not selected.
