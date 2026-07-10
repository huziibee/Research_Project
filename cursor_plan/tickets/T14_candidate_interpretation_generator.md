# T14 — Candidate interpretation generator

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Implement the candidate interpretation generator component.

## Component responsibility

Given command + context, generate possible meanings the user could intend. It should not decide final route by itself.

Example input:

```text
Move that thing over there.
```

Example output:

```json
[
  {"candidate_id":"c1","resolved_interpretation":"Move the red cup to the counter.","intent":"move_object","slots":{"object":"red cup","destination":"counter"},"plausibility":"high"},
  {"candidate_id":"c2","resolved_interpretation":"Move the knife to the table.","intent":"move_object","slots":{"object":"knife","destination":"table"},"plausibility":"medium"}
]
```

## Required tasks

1. Implement candidate generator interface.
2. Support rule/template mode for tests.
3. Support LLM-backed mode through `ModelClient` if available.
4. Include context fields in prompt/input.
5. Validate candidate IDs are unique.
6. Add tests for empty/no candidate cases and multiple candidates.

## Deliverables

- Candidate generator module.
- Prompt/template if LLM-backed.
- Tests.
- Completion report.

## Acceptance criteria

- Component can return zero, one, or many candidates.
- Candidate output validates against schema substructure.
- It does not choose final `recommended_strategy`.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after component tests. Do not implement router.
