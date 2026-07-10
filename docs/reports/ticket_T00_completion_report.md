# Ticket completion report

## Ticket
- ID: T00
- Title: Project scaffold and repository safety

## Preconditions checked
- `cursor_plan/` present at repository root; global contract, context-refresh
  protocol, dataset roles, hardware strategy, master plan, and refinement
  summary read.
- `data/raw/` present and treated as immutable.
- No pre-existing `src/`, `tests/`, `scripts/`, `configs/`, `docs/`, or
  `outputs/` scaffold.
- Verified on disk that IndirectRequests/SafeAgentBench Arrow files and the
  VAGUE parquet are real payloads (magic bytes, sizes), not Git LFS pointers or
  metadata stubs; reconciled against `git ls-files data/raw`.

## Files created/changed
Created (root):
- `pyproject.toml`
- `.gitignore`
- `README.md`

Created (package):
- `src/ambiguity_manager/__init__.py`
- `src/ambiguity_manager/paths.py`
- `src/ambiguity_manager/io_guard.py`

Created (tests):
- `tests/test_paths.py`
- `tests/test_io_guard.py`
- `tests/test_import.py`
- `tests/fixtures/.gitkeep`

Created (config/docs):
- `configs/README.md`
- `scripts/README.md`
- `docs/decisions/README.md`
- `docs/dataset_cards/README.md`
- `docs/reports/raw_dataset_inspection_2026-07-10.md`
- `docs/reports/ticket_T00_completion_report.md`

Created (directory markers):
- `data/interim/.gitkeep`
- `data/processed/.gitkeep`
- `data/annotations/.gitkeep`
- `data/splits/.gitkeep`
- `outputs/.gitkeep`

Modified: none.
Files under `data/raw/`: none created, modified, moved, deleted, or untracked.

## Tests written first, if TDD applies
- Test files: `tests/test_paths.py`, `tests/test_io_guard.py`, `tests/test_import.py`.
- Initial failing behavior: all tests errored with
  `ModuleNotFoundError: No module named 'ambiguity_manager'` because the package
  did not yet exist (Red phase). Recorded before implementation.
- TDD covered: `repo_root()` upward search (happy path, nested start, missing
  marker), `ProjectPaths` resolution and scaffold creation, and raw-path guard
  behaviour (see coverage list below).

## Commands run
- Red phase: `python -m unittest discover -s tests -v` (with `PYTHONPATH=src`) → FAILED (errors=3).
- Green phase: `python -m unittest discover -s tests -v` (with `PYTHONPATH=src`) → OK (19 tests).
- `git ls-files data/raw` → 1,939 tracked paths (reported; unchanged after T00).
- `git status --short` → only new scaffold files untracked; no `data/raw` file changes.

## Validation results
- 19 tests pass, 0 failures. Windows case-variation and junction guard tests
  executed (not skipped) on this Windows host.
- `data/raw` tracked count unchanged at 1,939 before and after implementation.

## Acceptance criteria status
- [x] Package imports successfully (`import ambiguity_manager`).
- [x] Test suite passes (`python -m unittest discover -s tests`).
- [x] No dataset conversion, model, metrics, or schema logic implemented.
- [x] Repository has the minimum directories needed by later tickets.
- [x] `repo_root()` locates the root by searching upward for `pyproject.toml`.
- [x] Central path module (`paths.py`); no hard-coded absolute paths; Windows-safe via `pathlib`.
- [x] Raw-write guard implemented and documented as API-level protection only.
- [x] Raw-guard tests cover: `data/raw` itself, nested paths, `..` traversal,
  relative and absolute paths, `data/raw_backup` allowed, Windows case
  variations, and junction resolution.
- [x] `.gitignore` ignores envs/caches/outputs/models/secrets and `data/raw/**`;
  does not ignore configs/tests/docs/manifests.
- [x] `git ls-files data/raw` reported; already-tracked raw files left untouched.
- [x] Inspection snapshot saved and labelled as manual (not a T02 replacement).
- [x] `scripts/README.md`, `docs/decisions/README.md`, `docs/dataset_cards/README.md` added.
- [x] Completion report written.

## Row counts / metric outputs, if applicable
Not applicable (no data processing in T00).

## Evidence and traceability
- Test command: `python -m unittest discover -s tests` (repo root; `pyproject.toml` sets `pythonpath = ["src"]` for pytest, and `PYTHONPATH=src` used for the unittest run).
- Red result: `Ran 3 tests ... FAILED (errors=3)`.
- Green result: `Ran 19 tests in 0.090s ... OK`.
- Raw payload verification: Arrow magic `FF FF FF FF`, Parquet magic `PAR1`, no `version https://git-lfs...` pointers.
- Output paths: see "Files created/changed".

## Unresolved TODO_VERIFY / BLOCKED items
- `data/raw/.venv/` (1,904 paths) and dataset payloads remain tracked in Git.
  Untracking requires a separate, explicit decision (not part of T00).
- Dependency installation deferred: `pytest`/`ruff`/`mypy` are configured in
  `pyproject.toml` but not installed; the suite runs on the standard library via
  `unittest`.
- Label mappings, licence terms, and row-level schema verification deferred to
  T01–T08.

## Stage gate
PASS/FAIL: PASS
Reason: All T00 acceptance criteria are satisfied and all 19 tests pass. No
files under `data/raw/` were modified. Schema (T01) and audit (T02) work was not
started.
