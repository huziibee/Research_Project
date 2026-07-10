# T23 — Optional fine-tuning smoke test

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Run an optional tiny fine-tuning smoke test only after schema, splits, evaluator, and local model setup are complete.

## Fine-tuning boundary

This is not final training. It proves the training loop works.

## Preconditions

Do not start unless:

- T12 splits exist,
- T20 evaluator exists,
- T22 local model setup is successful or a remote training environment is approved,
- human explicitly approves fine-tuning smoke test.

## Required tasks

1. Select 20–50 training examples from train split only.
2. Select 10 dev examples from dev split only.
3. Use adapter/LoRA/QLoRA-style setup if supported.
4. Train minimally.
5. Save adapter/model artifacts under timestamped output folder.
6. Run evaluator on tiny dev sample.
7. Document memory usage, runtime, and failures.

## Deliverables

- Fine-tuning smoke script/config.
- Tiny training output.
- Smoke evaluation report.
- Completion report.

## Acceptance criteria

- No test/gold examples used.
- Training does not overwrite base model or previous adapters.
- Smoke run either succeeds or documents clear blocker.
- No final performance claim is made.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after smoke report. Do not run full fine-tuning.
