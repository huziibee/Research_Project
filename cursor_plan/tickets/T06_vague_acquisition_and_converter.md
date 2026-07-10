# T06 — VAGUE acquisition check and converter

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Acquire/verify VAGUE files and build a converter only if the real files are present.

## Why this ticket exists

VAGUE is useful for visual/world-context disambiguation: ambiguous expression + scene context -> intended interpretation. It is not currently guaranteed to be in uploaded files.

## Dataset role

Use for:

- intent correctness,
- context benefit,
- route choice between `clarify` and `silently_resolve`,
- scene-context disambiguation.

If images are present but no LVLM is planned, prefer converting available captions/scene descriptions. Do not require LVLM in this ticket.

## Required tasks

1. Search repo/data folders for VAGUE files.
2. If not found:
   - create `docs/mapping/vague_acquisition_notes.md`,
   - list exact missing files needed,
   - mark ticket `BLOCKED_WAITING_FOR_DATA`,
   - stop.
3. If found:
   - inspect fields for utterance, scene/image/caption, candidate interpretations, gold interpretation,
   - document mapping.
4. Implement converter to canonical schema.
5. Set `label_confidence` based on source fields.
6. Write output to `data/interim/vague.jsonl`.
7. Validate schema and produce row-count report.

## Deliverables

- Acquisition notes if missing OR converter if present.
- Mapping report.
- Converted JSONL if present.
- Row-count report if present.
- Completion report.

## Acceptance criteria

- Missing data is handled explicitly without fake rows.
- If converted, VAGUE records preserve candidate/gold interpretation information.
- Visual context assumptions are documented.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after missing-data report or validated converter.
