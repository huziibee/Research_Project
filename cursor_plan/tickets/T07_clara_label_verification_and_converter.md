# T07 — CLARA label verification and conditional converter

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Verify CLARA label meanings before using CLARA. Build converter only if label mapping is confirmed from source metadata or documentation present in the repo.

## Why this ticket exists

CLARA may support clear/ambiguous/infeasible routing, but numeric labels cannot be guessed.

## Required tasks

1. Locate CLARA standardized file from T02 audit.
2. Inspect metadata fields and label distribution.
3. Search repo/docs for CLARA label documentation.
4. If label meanings cannot be verified:
   - create `docs/mapping/clara_label_verification_report.md`,
   - mark `TODO_VERIFY_LABEL_MAPPING`,
   - stop without creating final converted labels.
5. If verified:
   - document label mapping to route labels,
   - implement converter,
   - output `data/interim/clara.jsonl`,
   - report row counts and skipped rows.

## Deliverables

- Label verification report.
- Converter only if verified.
- Converted JSONL only if verified.
- Row-count report only if verified.
- Completion report.

## Acceptance criteria

- No numeric label is mapped by guesswork.
- If conversion occurs, all records pass schema validation.
- If mapping is unknown, ticket stops cleanly.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after label verification/conversion. Do not use CLARA in final metrics until verified.
