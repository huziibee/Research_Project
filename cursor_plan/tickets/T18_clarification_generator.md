# T18 — Targeted clarification generator

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Implement targeted clarification question generation.

## Component responsibility

Given missing slots/ambiguity types/candidates, generate a specific clarification question.

Bad:

```text
Can you clarify?
```

Good:

```text
Which object should I move, and where should I put it?
```

## Required tasks

1. Implement clarification generator interface.
2. Support template/rule mode for common missing slots:
   - object,
   - destination/location,
   - time,
   - quantity,
   - preference,
   - safety_precondition,
   - capability.
3. Support candidate contrast questions when multiple candidates exist.
4. Support safety-boundary clarification when some candidates are unsafe.
5. Add tests for each missing-slot type.

## Deliverables

- Clarification generator module.
- Tests.
- Completion report.

## Acceptance criteria

- Questions target specific missing fields.
- Safety-precondition questions are not generic rejections.
- Multiple candidate questions mention the distinction when possible.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after tests. Do not build evaluator yet.
