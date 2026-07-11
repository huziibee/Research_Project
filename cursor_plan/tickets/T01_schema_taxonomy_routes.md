# T01 — Canonical schema, taxonomy, and route labels

**Status:** COMPLETED — do not rerun unless a later audit identifies a concrete defect.**

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Implement the canonical schema, label enums, route enums, and validation helpers.

## Why this ticket exists

All later dataset converters, manager outputs, and evaluator metrics must agree on one schema. This prevents label drift and fake mappings.

## Required schema concepts

Input fields:

```json
{
  "command": "string",
  "scene_context": "string | null",
  "dialogue_history": ["string"],
  "capability_context": "string | null"
}
```

Gold/prediction fields:

```json
{
  "id": "string",
  "source_dataset": "string",
  "source_id": "string | null",
  "original_split": "string | null",
  "command": "string",
  "scene_context": "string | null",
  "dialogue_history": ["string"],
  "capability_context": "string | null",
  "candidate_interpretations": [],
  "ambiguity_present": true,
  "ambiguity_types": [],
  "primary_ambiguity_type": "string | null",
  "compound_ambiguity": false,
  "compound_ambiguity_count": 0,
  "missing_slots": [],
  "risk_relevant": false,
  "risk_level": "none | low | medium | high | unknown_until_clarified | null",
  "capability_status": "capable | incapable | uncertain | null",
  "recommended_strategy": "execute | clarify | silently_resolve | face_preserving_rejection | multi_step",
  "strategy_sequence": [],
  "gold_clarification_question": "string | null",
  "clarification_subtype": "string | null",
  "resolved_interpretation": "string | null",
  "intent": "string | null",
  "slots": {},
  "label_confidence": "gold_from_source | weak_derived | manual_gold | TODO_VERIFY",
  "mapping_notes": "string | null"
}
```

## Required tasks

1. Create schema module in `src/ambiguity_manager/schema/`.
2. Define allowed route labels.
3. Define allowed ambiguity labels.
4. Define data model using dataclasses, Pydantic, or plain validation functions.
5. Add validation for required fields and allowed enums.
6. Add serialization helpers for JSONL.
7. Create a sample valid record under `tests/fixtures/`.
8. Add tests for valid/invalid labels, required fields, and JSONL round trip.

## Deliverables

- Schema module.
- Label enum definitions.
- JSONL read/write helpers.
- Tests for schema validation.
- `docs/reports/ticket_T01_completion_report.md`.

## Acceptance criteria

- Invalid route labels fail validation.
- Invalid ambiguity labels fail validation.
- A valid example serializes/deserializes without losing fields.
- No dataset-specific logic appears in schema module.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after schema tests pass. Do not implement converters.

## Additional schema requirements

The canonical record must distinguish:

- `risk_level`: `low | medium | high | null`;
- `capability_status`: `capable | partially_capable | incapable | unknown | null`;
- `recommended_strategy` from the five frozen route labels;
- `strategy_sequence` for `multi_step`;
- `group_id` for split isolation;
- `annotation_status`: `source_native | weak_mapped | manually_annotated | adjudicated`;
- `label_eligibility` per metric family;
- `mapping_version` and source licence reference.

Define route precedence and tie-breaking rules, especially where safety/capability conflicts with clarification. Add schema invariants and tests for every enum, nullability rule, and multi-step sequence constraint.
