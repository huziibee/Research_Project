# T03 — AmbiK converter

**Status:** COMPLETED — do not rerun unless a later audit identifies a concrete defect.**

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Build the converter for **AmbiK** into the canonical schema.

## Why this ticket exists

This dataset contributes: embodied ambiguity, clarification, and safety-precondition ambiguity.

## Required source assumptions

Use the dataset audit from T02. Do not assume fields that are not present. If required fields are missing, write `BLOCKED_TODO_VERIFY` in the completion report.

## Mapping rules


Expected useful fields from planning: metadata may include `ambiguity_type`, `question`, `answer`, `user_intent`, `variants`, `unambiguous_direct`, `unambiguous_indirect`, `plan_for_clear_task`, and `plan_for_amb_task`.

Suggested mapping, only if fields exist:

- `metadata.ambiguity_type = safety` -> `ambiguity_types = ["safety_precondition"]`, `risk_relevant = true`, `recommended_strategy = "clarify"`.
- Other AmbiK ambiguity types map to project taxonomy only with documented mapping rules.
- `metadata.question` -> `gold_clarification_question`.
- `metadata.user_intent` may help `intent`, but do not overclaim if it is not structured.
- `label_confidence = gold_from_source` for source-provided question/ambiguity fields, `weak_derived` for route mappings.


## Required tasks

1. Locate the audited AmbiK file.
2. Implement a converter under `src/ambiguity_manager/data/` or `scripts/`.
3. Convert rows into canonical schema records.
4. Preserve provenance: `source_dataset`, `source_id`, `original_split`, raw metadata summary or mapping notes.
5. Assign `label_confidence` correctly.
6. Write JSONL to `data/interim/ambik.jsonl`.
7. Write conversion report to `docs/mapping/ambik_mapping_report.md`.
8. Write row-count JSON to `outputs/metrics/ambik_conversion_counts.json`.
9. Add tests/smoke test for at least 3 converted records.

## Deliverables

- Converter code.
- Converted JSONL.
- Mapping report.
- Row-count report.
- Tests/smoke validation.
- Completion report.

## Acceptance criteria

- Input rows, output rows, skipped rows, and skip reasons are reported.
- No silent row loss.
- All output records pass canonical schema validation.
- Unknown mappings are marked `TODO_VERIFY`, not guessed.
- No final benchmark metrics are produced in this ticket.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after converter is validated. Do not build weak pool or metrics.
