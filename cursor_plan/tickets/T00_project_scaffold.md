# T00 — Project scaffold and repository safety

**Status:** COMPLETED — do not rerun unless a later audit identifies a concrete defect.**

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Create the repository scaffold and safe project structure without implementing project logic yet.

## Why this ticket exists

Cursor should not start by building models or metrics. The project needs stable folders, config, logging, reports, and test structure first.

## Required tasks

1. Inspect the current repository/file tree.
2. Create the expected folders if missing:

```text
data/raw/
data/interim/
data/processed/
data/manual/
data/gold/
data/splits/
docs/reports/
docs/mapping/
docs/annotation/
outputs/logs/
outputs/metrics/
outputs/predictions/
src/ambiguity_manager/
src/ambiguity_manager/data/
src/ambiguity_manager/schema/
src/ambiguity_manager/models/
src/ambiguity_manager/routing/
src/ambiguity_manager/evaluation/
src/ambiguity_manager/safety_interface/
tests/
scripts/
```

3. Create a minimal Python package scaffold.
4. Add `README.md` if absent, describing project scope.
5. Add `.gitignore` entries for large data/model/output artifacts.
6. Add minimal dependency file (`requirements.txt` or `pyproject.toml`) with only essentials.
7. Add a simple smoke test that imports the package.

## Deliverables

- Repo folder structure.
- Minimal package import.
- `README.md` with scope boundary.
- Dependency file.
- `tests/test_import.py` or equivalent.
- Completion report at `docs/reports/ticket_T00_completion_report.md`.

## Acceptance criteria

- Package imports successfully.
- Test suite or import smoke test passes.
- No dataset conversion, model logic, or metrics logic implemented yet.
- Repo has directories needed by later tickets.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after scaffold is validated. Do not proceed to schema work.

## Additional required scaffold

Create versioned locations for:

```text
docs/decisions/
docs/dataset_cards/
docs/protocols/
outputs/statistics/
outputs/ablations/
outputs/robustness/
outputs/cost_sensitive/
outputs/manifests/
tests/fixtures/
```

Add a single project test command and a lightweight lint/type-check command where practical. Configure generated data, model weights, and large outputs so they are not accidentally committed.
