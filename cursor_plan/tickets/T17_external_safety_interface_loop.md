# T17 — External safety interface and loop-back behavior

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Implement the external safety module interface and loop-back behavior.

## Project boundary

This project does not own full safety classification. It sends candidate interpretations to an external safety interface and consumes the response.

## Core rule

Safety can eliminate interpretations. Safety should not invent the intended interpretation.

## Required safety responses

```text
allow
reject
needs_disambiguation
```

Per-candidate response shape:

```json
{
  "candidate_id": "c1",
  "safety_decision": "allow | reject | needs_disambiguation",
  "risk_level": "low | medium | high | unknown",
  "reason": "string | null",
  "missing_information": []
}
```

## Required tasks

1. Implement safety interface types.
2. Implement mock safety module for tests.
3. Implement routing behavior after safety response:
   - all rejected -> `face_preserving_rejection`,
   - one allowed but low support -> `clarify`,
   - one allowed and high support -> `execute`,
   - multiple allowed -> `clarify`,
   - needs disambiguation -> clarification loop.
4. Add tests for each case.

## Deliverables

- Safety interface module.
- Mock safety implementation.
- Router integration tests.
- Completion report.

## Acceptance criteria

- Safety rejection does not automatically select another candidate unless support is high.
- `needs_disambiguation` loops to clarification.
- No real safety classifier is implemented.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after safety loop tests. Do not build final experiments.
