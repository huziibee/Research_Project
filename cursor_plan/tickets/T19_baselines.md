# T19 — Baseline systems

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Implement baselines for comparison.

## Why this ticket exists

Without baselines, metrics are not meaningful.

## Required baselines

1. Always clarify.
2. Always silently resolve.
3. Direct LLM JSON baseline from T13.
4. Context-blind manager: same manager but scene/dialogue removed.
5. Proposed manager: full candidate/context/safety-loop flow.

Optional safety-specific baseline:

- Interpret once then safety-check.

## Required tasks

1. Implement baseline runner interface.
2. Ensure every baseline emits canonical prediction schema.
3. Add smoke tests for each baseline.
4. Save predictions under `outputs/predictions/<baseline_name>/`.
5. Do not compute final metrics yet unless evaluator exists and this ticket explicitly calls it only for smoke.

## Deliverables

- Baseline implementations.
- Baseline smoke tests.
- Completion report.

## Acceptance criteria

- Every baseline can run on a tiny sample.
- Every output validates against schema.
- Baseline names and configs are logged.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after baseline smoke tests. Do not run full experiments.

## Mandatory baseline set

Implement and evaluate all of the following:

1. always execute;
2. always clarify;
3. always silently resolve;
4. direct structured LLM interpretation;
5. **degree-based routing** using ambiguity severity/uncertainty thresholds without explicit ambiguity-type semantics;
6. context-blind variant of the proposed manager as an ablation;
7. full type-and-risk-aware manager.

Degree-based thresholds must be selected using train/dev only and frozen before test evaluation. The context-blind manager is not a substitute for degree-based routing.
