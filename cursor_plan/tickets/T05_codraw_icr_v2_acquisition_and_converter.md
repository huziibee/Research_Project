# T05 — CoDraw-iCR v2 acquisition check and converter

**Status:** COMPLETED — do not rerun unless a later audit identifies a concrete defect.**

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Acquire/verify CoDraw-iCR v2 files and build a converter only if the real files are present.

## Why this ticket exists

CoDraw-iCR v2 is valuable for scene + dialogue grounded clarification. It is not currently guaranteed to be in the uploaded files. Cursor must not fake it.

## Dataset role

Use for:

- clarification precision/recall/F1,
- clarification target accuracy,
- slot/attribute/location binding,
- context benefit from dialogue and scene.

Do not claim it is a gold compound-ambiguity dataset.

## Required tasks

1. Search repo/data folders for CoDraw-iCR v2 files.
2. If not found:
   - create `docs/mapping/codraw_icr_v2_acquisition_notes.md`,
   - list exact missing files needed,
   - mark ticket `BLOCKED_WAITING_FOR_DATA`,
   - stop.
3. If found:
   - inspect file structure,
   - identify fields for instruction, dialogue history, scene/items, clarification request, clarification target/content,
   - document mapping.
4. Implement converter to canonical schema.
5. Preserve provenance and source IDs.
6. Write output to `data/interim/codraw_icr_v2.jsonl`.
7. Validate schema and produce row-count report.

## Deliverables

- Acquisition notes if missing OR converter if present.
- Mapping report.
- Converted JSONL if present.
- Row-count report if present.
- Completion report.

## Acceptance criteria

- If files are missing, Cursor stops cleanly and does not create fake converted records.
- If files are present, all output records pass canonical schema validation.
- Clarification targets are mapped only when source supports them.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after missing-data report or validated converter. Do not proceed to VAGUE.
