# T13 — Direct prompted JSON baseline

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Implement a direct prompted JSON LLM baseline behind a model adapter interface.

## Why this ticket exists

Before building the full manager, establish a baseline: same input, direct JSON output.

## Required tasks

1. Implement `ModelClient` abstraction with `generate_json(prompt, schema)`.
2. Provide at least one safe dummy/mock model for tests.
3. Add optional provider/local endpoint hooks without hard-coding secrets.
4. Implement prompt template for direct LLM ambiguity routing.
5. Enforce JSON parsing and schema validation.
6. Save raw outputs and parsed predictions separately.
7. Add retry/repair only if transparent and logged.
8. Run on a tiny sample split if available.

## Deliverables

- Model adapter interface.
- Direct JSON baseline runner.
- Prompt template.
- Output writer under `outputs/predictions/`.
- Tests using mock model.
- Completion report.

## Acceptance criteria

- Mock model tests pass without external API.
- Invalid JSON is handled explicitly.
- Predictions validate against schema or are logged as invalid.
- No final results are claimed from tiny smoke runs.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after direct JSON baseline smoke test. Do not build full manager components.

## Baseline freeze requirements

- Use train/dev only for prompt design and few-shot selection.
- Version and hash every prompt.
- Freeze the selected prompt before any protected test execution.
- Enforce JSON schema and count repair attempts, invalid outputs, and fallback behavior.
- Keep deterministic decoding for the primary run where supported.
