# T04 — IndirectRequests converter

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Build the converter for **IndirectRequests** into the canonical schema.

## Why this ticket exists

This dataset contributes: pragmatic ambiguity, implied intent, and slot inference.

## Required source assumptions

Use the dataset audit from T02. Do not assume fields that are not present. If required fields are missing, write `BLOCKED_TODO_VERIFY` in the completion report.

## Mapping rules


Expected useful fields from planning: metadata may include `slot_description`, `possible_slot_values`, `target_slot_value`, and `mean_world_understanding`.

Suggested mapping, only if fields exist:

- Use command as indirect/pragmatic utterance.
- `ambiguity_types` should usually include `pragmatic` and/or `contextual`/`preference` only when justified by source fields.
- `target_slot_value` -> relevant slot value when it is not ambiguous/unknown.
- `slot_description` -> slot key description, normalized where possible.
- `resolved_interpretation` may be derived only if source gives enough information; otherwise leave null and mark weak.
- `recommended_strategy` can be `silently_resolve` only if target slot is clear from source metadata; otherwise `clarify` or `TODO_VERIFY`.


## Required tasks

1. Locate the audited IndirectRequests file.
2. Implement a converter under `src/ambiguity_manager/data/` or `scripts/`.
3. Convert rows into canonical schema records.
4. Preserve provenance: `source_dataset`, `source_id`, `original_split`, raw metadata summary or mapping notes.
5. Assign `label_confidence` correctly.
6. Write JSONL to `data/interim/indirect_requests.jsonl`.
7. Write conversion report to `docs/mapping/indirect_requests_mapping_report.md`.
8. Write row-count JSON to `outputs/metrics/indirect_requests_conversion_counts.json`.
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
