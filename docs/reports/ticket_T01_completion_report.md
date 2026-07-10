# Ticket completion report

## Ticket
- ID: T01
- Title: Canonical schema, taxonomies, and validation contracts

## Preconditions checked
- T00 scaffold present (`paths`, `io_guard`, 19 passing tests).
- Approved decisions D1–D6 and D8 applied; stdlib-only (D3); no Pydantic.
- `record_class` limited to `source_converted` and `adjudicated_gold` only.
- No route precedence frozen; no prediction schema or prediction JSONL.
- `data/raw/` not modified.

## Files created/changed

### Created
- `src/ambiguity_manager/schema/__init__.py`
- `src/ambiguity_manager/schema/version.py`
- `src/ambiguity_manager/schema/taxonomies.py`
- `src/ambiguity_manager/schema/errors.py`
- `src/ambiguity_manager/schema/records.py`
- `src/ambiguity_manager/schema/validation.py`
- `src/ambiguity_manager/schema/jsonl.py`
- `tests/test_schema_validation.py`
- `tests/test_schema_jsonl.py`
- `tests/fixtures/canonical_record_minimal.json`
- `tests/fixtures/canonical_record_compound_multistep.json`
- `docs/reports/ticket_T01_completion_report.md`

### Modified
- `src/ambiguity_manager/__init__.py` (docstring only)

### Not modified
- `data/raw/**`
- Converters, annotations, splits, models, metrics, routing policy

## Tests written first, if TDD applies
- Test files: `tests/test_schema_validation.py`, `tests/test_schema_jsonl.py`
- Initial failing behavior (Red phase):
  - `python -m unittest discover -s tests -v` with `PYTHONPATH=src`
  - **28 errors**, all `ModuleNotFoundError: No module named 'ambiguity_manager.schema'`
  - Pre-existing T00 tests: 19 passed

## Commands run
- Red: `python -m unittest discover -s tests -v` → FAILED (errors=28)
- Green: `python -m unittest discover -s tests -v` → OK (47 tests)

## Validation results
- 47 tests pass, 0 failures (19 T00 + 28 T01).
- Canonical JSONL write rejects paths under `data/raw` via `resolve_writable_path`.
- Valid fixtures round-trip without field loss.
- Duplicate `id` rejected on JSONL batch load.
- `record_class=prediction` rejected at parse time.

## Acceptance criteria status
- [x] Schema module in `src/ambiguity_manager/schema/`
- [x] Frozen route labels (5) with validation
- [x] Frozen ambiguity labels (10) with multi-label support
- [x] `risk_level`: none, low, medium, high, unknown_until_clarified, null
- [x] `capability_status`: capable, partially_capable, incapable, unknown, null
- [x] `record_class`: source_converted, adjudicated_gold only (no prediction)
- [x] `split_status` with default `unsplit`
- [x] Compound ambiguity invariants enforced
- [x] `multi_step` requires `strategy_sequence` length ≥ 2; repeats allowed
- [x] Non-`multi_step` routes forbid non-empty `strategy_sequence`
- [x] Provenance and `label_eligibility` validated
- [x] `TODO_VERIFY` cannot enable metric eligibility
- [x] Adjudicated vs source-converted annotation invariants
- [x] JSON/JSONL round-trip helpers for canonical dataset records only
- [x] No dataset-specific logic in schema module
- [x] No converters, annotations, splits, models, metrics, or routing policy
- [x] No writes to `data/raw/`
- [x] Completion report written

## Row counts / metric outputs, if applicable
Not applicable.

## Evidence and traceability
- Schema version: `1.0.0` (`CANONICAL_SCHEMA_VERSION`)
- Test command: `PYTHONPATH=src python -m unittest discover -s tests -v`
- Fixtures: `tests/fixtures/canonical_record_minimal.json`, `canonical_record_compound_multistep.json`

## Unresolved TODO_VERIFY / BLOCKED items
- `PredictionRecord` / model output schema deferred to evaluation/model tickets.
- Route precedence and routing-policy behaviour deferred to T15.
- Per-dataset field mappings deferred to T03–T09.
- Git commit not performed (per user instruction).

## Stage gate
PASS/FAIL: **PASS**

Reason: All T01 acceptance criteria satisfied; 47/47 tests pass; no `data/raw` changes; scope limited to canonical schema, taxonomies, validation, and dataset JSONL helpers.
