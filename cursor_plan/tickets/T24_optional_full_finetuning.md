# T24 — Optional full fine-tuning

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Run optional full fine-tuning only if the smoke test succeeded and the human approves.

## Preconditions

Required:

- T23 smoke test passed,
- final train/dev/test splits locked,
- no unresolved schema changes,
- human approval recorded in report.

## Required tasks

1. Freeze dataset splits.
2. Save training config.
3. Train on train split only.
4. Tune only on dev split.
5. Evaluate once on test/gold after configuration is frozen.
6. Save model/adapters with timestamp.
7. Compare against prompted baseline and rule-assisted manager.
8. Report whether fine-tuning actually improves metrics.

## Deliverables

- Training config.
- Model/adapters.
- Dev and test metrics.
- Comparison report.
- Completion report.

## Acceptance criteria

- No test leakage.
- Metrics are computed by evaluator from saved predictions.
- If fine-tuning underperforms, report honestly.
- Model artifacts are not too large for repo; store path and ignore if needed.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after comparison report. Do not do failure analysis here.
