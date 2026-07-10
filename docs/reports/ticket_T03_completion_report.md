# Ticket completion report

## Ticket
- ID: T03
- Title: AmbiK source analysis, label mapping decision, canonical converter, validation, and row-accounting evidence

## Preconditions checked
- T00 scaffold (`paths`, `io_guard`), T01 canonical schema (v1.0.0), and T02
  audit present; full suite green before T03 (78 tests).
- `data/raw/` treated as immutable; AmbiK primary CSV payload verified in T02.
- Only `data/raw/AmbiK/AmbiK_data.csv` is authoritative for T03; auxiliary AmbiK
  CSVs are excluded.
- Approved decisions applied: O1 (paths), O2 (ambiguity mapping), O3
  (`resolved_interpretation = unambiguous_direct`), O4 (`scene_context =
  environment_full`), O5 (`risk_relevant` true only for `safety_precondition`),
  O6 (`recommended_strategy` null / `strategy_sequence` empty), O7 (register not
  modified), O8 (`intent_slots` eligibility false).
- Required corrections applied: record-level `weak_mapped` / `weak_derived`;
  `ambiguity` + `clarification_target` eligibility kept as mapped-source;
  list-like fields preserved as raw strings (no parsing); all 15 source columns
  preserved verbatim in `source_metadata`.

## Files created/changed

### Created
- `src/ambiguity_manager/converters/__init__.py`
- `src/ambiguity_manager/converters/ambik.py`
- `scripts/convert_ambik.py`
- `tests/test_ambik_converter.py`
- `tests/fixtures/ambik/tiny_ambik.csv`
- `tests/fixtures/ambik/bad_header_ambik.csv`
- `tests/fixtures/ambik/unknown_type_ambik.csv`
- `tests/fixtures/ambik/quarantine_ambik.csv`
- `tests/fixtures/ambik/dup_id_ambik.csv`
- `docs/mapping/ambik_mapping.md`
- `docs/reports/ticket_T03_completion_report.md`

### Generated (git-ignored data/outputs)
- `data/interim/ambik/ambik_canonical.jsonl`
- `data/interim/ambik/ambik_quarantine.jsonl` (empty; 0 quarantined)
- `outputs/metrics/ambik_conversion_summary.json`

### Not modified
- `data/raw/**`
- `src/ambiguity_manager/schema/**` (schema v1.0.0 unchanged)
- `configs/datasets/*.json` (curated register/manifest unchanged)
- Auxiliary AmbiK CSV files

## Tests written first (TDD)
- Test file: `tests/test_ambik_converter.py`
- Red phase: `PYTHONPATH=src python -m unittest tests.test_ambik_converter`
  -> `ModuleNotFoundError: No module named 'ambiguity_manager.converters'`
  (errors=1). Recorded before implementation.
- Green phase: 20 AmbiK tests pass; full suite 98 tests pass.

## Commands run
- Red: `PYTHONPATH=src python -m unittest tests.test_ambik_converter -v` -> FAILED (errors=1)
- Green (module): `PYTHONPATH=src python -m unittest tests.test_ambik_converter -v` -> OK (20 tests)
- Green (full): `PYTHONPATH=src python -m unittest discover -s tests` -> OK (98 tests)
- Conversion: `python scripts/convert_ambik.py` -> success
- Independent validation: reloaded and re-validated all 1000 output records.

## Validation results
- 1000/1000 output records pass `validate_canonical_record()` (both at write and
  on independent reload).
- Unique output IDs: 1000; ordering ascending by numeric `source_id`.
- `recommended_strategy`, `risk_level`, `capability_status` null on every record;
  `strategy_sequence` empty on every record.
- `risk_relevant=true` on exactly 155 records (safety_precondition only).
- Every record `annotation_status=weak_mapped`, `label_confidence=weak_derived`.
- Every record preserves all 15 source columns in `source_metadata`.
- Quarantine file empty; no silent row loss.
- Source SHA-256 matches T02 audit (`98bb4677eb7fad00…`).

## Acceptance criteria status
- [x] Converter reads only the AmbiK primary CSV
- [x] Exact 15-column header validated (mismatch raises)
- [x] Input/output/skipped/quarantined counts reported with reasons
- [x] No silent row loss (accounting invariant holds)
- [x] All output records pass canonical schema validation
- [x] Ambiguity mapping documented; unknown types quarantined, not guessed
- [x] No fabricated risk/capability/route/slot/compound values
- [x] `label_confidence` / `label_eligibility` per approved policy
- [x] Provenance preserved in `source_metadata`
- [x] Outputs written only via `resolve_writable_path`
- [x] `data/raw/` not modified
- [x] TDD red-green recorded
- [x] Full suite passes (98 tests)
- [x] Mapping doc contains no raw command text
- [x] Auxiliary AmbiK CSVs not processed
- [x] No final benchmark metrics produced

## Row counts / metric outputs
- source_rows_read: 1000
- rows_converted: 1000
- rows_skipped: 0
- rows_quarantined: 0
- output_ids_unique: 1000
- converted_by_ambiguity_type: preference=420, commonsense=425, safety_precondition=155

## Evidence and traceability
- Source: `data/raw/AmbiK/AmbiK_data.csv` (SHA-256 `98bb4677eb7fad00a58393aa751f833c5e01dcda9090fe0ef202272b20e2f531`)
- Mapping version: `ambik-1.0.0`; schema version: `1.0.0`
- Output: `data/interim/ambik/ambik_canonical.jsonl`
- Quarantine: `data/interim/ambik/ambik_quarantine.jsonl`
- Summary: `outputs/metrics/ambik_conversion_summary.json`
- Mapping doc: `docs/mapping/ambik_mapping.md`

## Unresolved TODO_VERIFY / BLOCKED items
- AmbiK licence remains `unresolved` (no licence file in raw tree); recorded, not invented.
- Register `mapping_confidence` stays `TODO_VERIFY` per O7 (not modified in T03);
  a follow-up decision may promote it now that mapping is implemented.
- Route / risk_level / capability / structured slots / intent remain null
  (deferred; not supported by source).
- Git commit not performed (per instruction).

## Stage gate
PASS/FAIL: **PASS**

Reason: All T03 acceptance criteria satisfied via TDD; 98/98 tests pass; 1000
AmbiK rows converted with zero loss and full schema validation; no fabricated
labels; `data/raw`, schema v1.0.0, and curated configs untouched.
