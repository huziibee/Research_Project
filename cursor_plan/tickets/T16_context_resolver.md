# T16 — Scene/dialogue context resolver

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Implement context resolver logic that uses scene context and dialogue history to reduce ambiguity when justified.

## Component responsibility

The context resolver checks whether scene or dialogue context makes one interpretation sufficiently supported.

Example:

- Command only: `Move that thing over there.` -> clarify.
- Command + prior dialogue saying red cup goes to counter -> may resolve to `Move the red cup to the counter.`

## Required tasks

1. Implement context resolver interface.
2. Add support for text scene context and dialogue history.
3. Add confidence/support fields such as `support = command | scene_context | dialogue_history | combined`.
4. Do not over-resolve when context is insufficient.
5. Add tests:
   - no context -> clarify,
   - clear scene context -> one candidate,
   - conflicting context -> clarify,
   - dialogue resolves referent -> execute candidate.

## Deliverables

- Context resolver module.
- Tests.
- Completion report.

## Acceptance criteria

- Context can reduce ambiguity only when supported.
- Conflicting context does not silently resolve.
- Resolver output feeds router but does not execute anything.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after context tests. Do not implement safety loop.
