# T26 — Final report artifacts and reproducibility summary

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Generate final report artifacts: tables, diagrams, and result summaries.

## Required tasks

1. Create final architecture diagram in Mermaid.
2. Create dataset role/row-count table from actual audit output.
3. Create metric table from actual evaluator outputs.
4. Create experiment comparison table.
5. Create failure analysis summary table.
6. Create limitations section notes.
7. Create reproducibility checklist.
8. Create `docs/reports/final_artifacts.md`.

## Deliverables

- Final artifact markdown file.
- Mermaid diagrams.
- Tables based on actual outputs.
- Reproducibility checklist.
- Completion report.

## Acceptance criteria

- Every result table traces back to actual output files.
- No fake metrics or unrun experiments.
- Limitations mention missing/unverified datasets and weak labels honestly.
- Diagrams match implemented architecture.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after final artifacts. Project implementation plan complete.

## Required experiment evidence package

Generate only from saved outputs:

- dataset composition and label-distribution tables;
- source licence and inclusion register summary;
- annotation-agreement table;
- full baseline comparison;
- risk/capability results;
- safety and cost-sensitive results;
- compound-command results;
- confidence intervals and significance tests;
- ablation results;
- robustness results;
- error-category breakdown;
- latency/resource table;
- limitations and negative-results register;
- reproducibility checklist and exact rerun commands.

Create/update `DATASET_CARD.md`, `EXPERIMENT_PROTOCOL.md`, `LIMITATIONS.md`, and `REPRODUCIBILITY.md`.
