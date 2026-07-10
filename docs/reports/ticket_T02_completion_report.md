# Ticket completion report

## Ticket
- ID: T02
- Title: Automated dataset audit, dataset inclusion register, licence/provenance manifest, and machine-readable audit outputs

## Preconditions checked
- T00 scaffold (`paths`, `io_guard`) and T01 canonical schema (v1.0.0) present.
- `data/raw/` treated as read-only; no raw files modified.
- Curated configs designated immutable audit inputs.
- Approved authority decisions applied (AmbiK primary CSV, CoDraw primary TSV, JSON configs, optional `pyarrow`).

## Files created/changed

### Created
- `src/ambiguity_manager/data_audit/__init__.py`
- `src/ambiguity_manager/data_audit/version.py`
- `src/ambiguity_manager/data_audit/models.py`
- `src/ambiguity_manager/data_audit/config.py`
- `src/ambiguity_manager/data_audit/readers.py`
- `src/ambiguity_manager/data_audit/checks.py`
- `src/ambiguity_manager/data_audit/runner.py`
- `src/ambiguity_manager/data_audit/report.py`
- `src/ambiguity_manager/data_audit/writer.py`
- `scripts/audit_datasets.py`
- `configs/datasets/dataset_inclusion_register.json`
- `configs/datasets/licence_provenance_manifest.json`
- `tests/test_dataset_audit.py`
- `tests/fixtures/dataset_audit/` (register/manifest fixtures, tiny payloads, malformed files, code-only/metadata-only fixtures)
- `docs/mapping/dataset_audit.md` (generated)
- `docs/decisions/dataset_inclusion_register.md` (generated)
- `docs/dataset_cards/source_licence_manifest.md` (generated)
- `outputs/metrics/dataset_audit.json` (generated; git-ignored)
- `docs/reports/ticket_T02_completion_report.md`

### Modified
- `pyproject.toml` — added optional `audit = ["pyarrow>=14"]` extra

### Not modified
- `data/raw/**`
- `src/ambiguity_manager/schema/**`
- Converters, annotations, splits, models, routing, metrics

## Tests written first, if TDD applies
- Test file: `tests/test_dataset_audit.py`
- Red phase (`PYTHONPATH=src python -m unittest tests.test_dataset_audit -v`):
  - **26 errors**, all `ModuleNotFoundError: No module named 'ambiguity_manager.data_audit'`
- Green phase (`PYTHONPATH=src python -m unittest discover -s tests -v`):
  - **73 tests OK** (47 pre-existing + 26 new)

## Commands run
- Red: `PYTHONPATH=src python -m unittest tests.test_dataset_audit -v` → FAILED (errors=26)
- Green: `PYTHONPATH=src python -m unittest discover -s tests -v` → OK (73 tests)
- Audit: `PYTHONPATH=src python scripts/audit_datasets.py` → success

## Validation results
- All 73 tests pass.
- Audit JSON validates against audit schema checks (no `sample_rows`, no raw record text).
- Curated JSON configs unchanged by audit execution.
- All writes routed through `resolve_writable_path`; `data/raw` not written.
- Parser-based counts for CSV/TSV/JSON/JSONL/Arrow IPC stream/Parquet metadata.
- Full streaming SHA-256 for all audited payload files.
- ClariQ train/dev overlap recorded as warning (`overlap_count=7`), not exclusion.

## Acceptance criteria status
- [x] `scripts/audit_datasets.py` runs read-only audit
- [x] `outputs/metrics/dataset_audit.json` produced via guarded write API
- [x] `configs/datasets/dataset_inclusion_register.json` curated and validated
- [x] `configs/datasets/licence_provenance_manifest.json` curated and validated
- [x] `docs/mapping/dataset_audit.md` generated summary
- [x] Companion markdown generated from configs + audit evidence
- [x] Parser-based record counts (no grep estimates)
- [x] Status taxonomy: verified / partially_verified / metadata_only / blocked / excluded / TODO_VERIFY
- [x] Licence tracked separately from technical verification
- [x] No licence terms invented; unresolved/stated_unverified recorded honestly
- [x] No dataset record content copied into JSON/Markdown
- [x] TDD red-green recorded
- [x] No converter/schema/model/metric work started
- [x] `data/raw/` untouched

## Row counts / metric outputs, if applicable

Per-dataset primary parser row counts (authoritative file only):

| Dataset | Verification | Primary rows | Notes |
|---|---|---:|---|
| AmbiK | TODO_VERIFY | 1,000 | Auxiliary: 900, 400, 100, 300 |
| CLARA | TODO_VERIFY | 5,345 | JSON dict records |
| ClariQ | partially_verified | 9,176 | 7 train/dev `question_id` overlaps (warning) |
| CoDraw-iCR v2 | TODO_VERIFY | 8,765 | Auxiliary raw TSV: 15,300 |
| IndirectRequests | TODO_VERIFY | 246 (train) | Validation 272, test 388 |
| SafeAgentBench | verified | 100 (abstract) | Subsets: 300 unsafe, 300 safe, 50 long |
| TEACh | excluded | 2,275 game JSON inventory | Policy excluded |
| teach_tatc | excluded | — | Code-only tree |
| VAGUE | TODO_VERIFY | 1,677 | Parquet metadata count |

Audit summary: verified=1, partially_verified=1, excluded=2, TODO_VERIFY=5, blocked=0, missing_not_blocking=5.

## Evidence and traceability
- Audit command: `PYTHONPATH=src python scripts/audit_datasets.py`
- Output JSON: `outputs/metrics/dataset_audit.json`
- Audit schema: `1.0.0`
- Git commit at audit time: recorded in audit JSON
- Submodule commits recorded where available (AmbiK, CLARA, ClariQ, TEACh, teach_tatc)

## Unresolved TODO_VERIFY / BLOCKED items
- All core/conditional datasets remain `TODO_VERIFY` for label/route mapping (expected until T03–T09).
- Licence status unresolved for most datasets; CoDraw/TEACh/teach_tatc `stated_unverified` only.
- `data/raw/.venv` still present (excluded from audit inventory; untracking deferred).
- Missing-not-blocking: Dynamic-RDMM, RefCOCO, ReferIt3D, CMC, manual compound extension.

## Stage gate
PASS/FAIL: **PASS**

Reason: T02 deliverables implemented with TDD, full audit executed, configs remain immutable inputs, and no scope leakage into converters or schema mapping.
