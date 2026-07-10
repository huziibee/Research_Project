# T08 — Optional ClariQ auxiliary converter

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Optionally convert ClariQ as an auxiliary clarification dataset, not as core robot ambiguity data.

## Why this ticket exists

ClariQ can help clarification question style and clarify/not-clarify behavior, but it is not embodied, scene-grounded, or robot-command specific.

## Required tasks

1. Locate ClariQ standardized file from T02 audit.
2. Inspect fields including `clarification_need`, `question`, `answer`, and `facet_desc` if present.
3. Document why ClariQ is auxiliary.
4. Implement converter only for fields supported by source.
5. Set `source_dataset = clariq` and `label_confidence` correctly.
6. Output to `data/interim/clariq_auxiliary.jsonl`.
7. Mark records with `mapping_notes = auxiliary_non_robotic_clarification`.

## Deliverables

- Optional converter.
- Converted auxiliary JSONL.
- Mapping report.
- Row-count report.
- Completion report.

## Acceptance criteria

- ClariQ is not mixed into core benchmark unless explicitly approved later.
- Converted records pass schema validation.
- Clarification question fields are preserved when available.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after auxiliary conversion. Do not use in core splits automatically.
