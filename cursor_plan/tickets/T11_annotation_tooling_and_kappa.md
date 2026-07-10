# T11 — Annotation tooling and Cohen kappa

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Build annotation tooling and Cohen's kappa calculation for the manual compound dataset.

## Why this ticket exists

Manual labels are subjective. Inter-annotator agreement is needed for rigor.

## Required tasks

1. Create an annotation input format for two annotators.
2. Implement validation of annotation files.
3. Implement Cohen's kappa for single-label fields:
   - `primary_ambiguity_type`
   - `recommended_strategy`
   - `risk_level` where applicable
   - `capability_status` where applicable
4. Implement multi-label agreement for `ambiguity_types`:
   - exact set agreement,
   - per-label F1 or Jaccard,
   - optional per-label kappa by converting each label to binary.
5. Create disagreement report listing examples where annotators differ.
6. Support adjudicated gold output after human resolution.

## Deliverables

- Annotation validation script.
- Kappa/agreement script.
- `docs/annotation/kappa_protocol.md`.
- Example run on seed data or tiny dummy annotation files.
- Completion report.

## Acceptance criteria

- Scripts do not require final manual dataset to exist.
- Dummy/seed kappa run completes.
- Disagreement report includes example IDs and differing fields.
- Adjudicated gold output format matches canonical schema.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after tooling works. Do not create final gold dataset unless annotation files exist and human approves.

## Agreement requirements

- Double-annotate a representative subset selected before adjudication.
- Include all route labels, all risk levels, all capability statuses, major ambiguity labels, and compound cases.
- Compute raw agreement and Cohen's kappa for single-label fields.
- For multi-label ambiguity, compute per-label kappa plus macro average and Jaccard/exact-set agreement.
- Report prevalence and category counts so kappa is interpretable.
- Preserve both original annotations, adjudicated labels, disagreement reasons, and adjudicator identity.
- Define an acceptance threshold before viewing the final agreement result; if not met, revise guidelines and repeat a fresh calibration subset.
