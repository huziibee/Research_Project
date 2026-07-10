# T09 — Weak labelled pool builder

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Build a weak labelled pool from validated converted datasets.

## Why this ticket exists

The weak pool is for prompting/training/exploration. It is not the final gold evaluation benchmark.

## Inputs

Use only converted JSONL files that exist and pass schema validation:

```text
data/interim/ambik.jsonl
data/interim/indirect_requests.jsonl
data/interim/codraw_icr_v2.jsonl if present
data/interim/vague.jsonl if present
data/interim/clara.jsonl if verified
data/interim/clariq_auxiliary.jsonl if present and explicitly included as auxiliary
```

## Required tasks

1. Discover existing converted JSONL files.
2. Validate every record.
3. Combine into `data/processed/weak_pool.jsonl`.
4. Preserve source provenance and label confidence.
5. Create source distribution report.
6. Create route distribution report.
7. Create ambiguity label distribution report.
8. Prevent accidental dominance from huge datasets by reporting source proportions; do not downsample unless explicitly configured.

## Deliverables

- `data/processed/weak_pool.jsonl`
- `outputs/metrics/weak_pool_distribution.json`
- `docs/reports/weak_pool_report.md`
- Completion report.

## Acceptance criteria

- Every record validates against canonical schema.
- Source counts match sum of included converted files minus documented skips.
- Weak pool is clearly labelled as not final gold benchmark.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after weak pool report. Do not create gold splits yet.

## Additional integrity rules

- Keep auxiliary records separable through explicit flags.
- Never allow weak project-inferred labels to become gold by merging.
- Produce per-field label-eligibility counts.
- Create a machine-readable manifest containing input file hashes and output hash.
- Add deterministic balancing configuration, but do not silently rebalance or downsample.
