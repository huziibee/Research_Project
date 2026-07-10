# Ticket completion report

## Ticket
- ID: T04
- Title: IndirectRequests source analysis, label-semantic decision, canonical converter, split preservation, validation, and row-accounting evidence

## Preconditions checked
- T00 scaffold (`paths`, `io_guard`), T01 canonical schema (v1.0.0), T02 audit, and T03
  AmbiK converter present; 102 tests green before T04 work began.
- `data/raw/IndirectRequests/{train,validation,test}/data-00000-of-00001.arrow`
  verified as Arrow IPC streams in T02.
- Approved mapping decisions O1–O6 and corrections A–H applied.
- Curated configs not modified (O7).

## Files created/changed

### Created
- `src/ambiguity_manager/converters/indirect_requests.py`
- `scripts/convert_indirect_requests.py`
- `tests/test_indirect_requests_converter.py`
- `tests/fixtures/indirect_requests/build_fixtures.py`
- `docs/mapping/indirect_requests_mapping.md`
- `docs/reports/ticket_T04_completion_report.md`

### Generated (git-ignored data/outputs)
- `data/interim/indirect_requests/indirect_requests_canonical.jsonl`
- `data/interim/indirect_requests/indirect_requests_quarantine.jsonl` (empty)
- `outputs/metrics/indirect_requests_conversion_summary.json`

### Not modified
- `data/raw/**`
- `src/ambiguity_manager/schema/**` (schema v1.0.0 unchanged)
- `configs/datasets/*.json`
- `src/ambiguity_manager/converters/ambik.py` and prior AmbiK outputs
- Model, routing, split-generation, or metric code

## Tests written first, if TDD applies
- Test file: `tests/test_indirect_requests_converter.py`
- Red phase: `PYTHONPATH=src python -m unittest tests.test_indirect_requests_converter -v`
  -> `ModuleNotFoundError: No module named 'ambiguity_manager.converters.indirect_requests'`
  (errors=1). Recorded before implementation.
- Green phase: 20 new IndirectRequests tests pass; full suite 122 tests pass.

## Commands run
- Red: `PYTHONPATH=src python -m unittest tests.test_indirect_requests_converter -v` -> FAILED (errors=1)
- Green (module): `PYTHONPATH=src python -m unittest tests.test_indirect_requests_converter -v` -> OK (20 tests)
- Green (full): `PYTHONPATH=src python -m unittest discover -s tests` -> OK (122 tests)
- Conversion: `PYTHONPATH=src python scripts/convert_indirect_requests.py` -> success
- Independent validation: reloaded and re-validated all 906 output records

## Validation results
- 906/906 output records pass `validate_canonical_record()` on independent reload.
- Unique output IDs: 906.
- `resolved_interpretation`, `capability_context`, and `group_id` are null on every record.
- `rows_ambiguous=162`, `rows_concrete_target=744` match expected accounting.
- Quarantine file empty; no silent row loss.
- Per-split SHA-256 values match T02 audit prefixes.

## Acceptance criteria status
- [x] Reads only the three authoritative Arrow IPC stream files
- [x] Uses `pyarrow.ipc.open_stream()` exclusively
- [x] Full row accounting; 906 = converted + skipped + quarantined
- [x] Official splits preserved; no merge/shuffle/resplit
- [x] Every output record passes canonical schema v1.0.0 validation
- [x] No fabricated route/risk/capability/compound/clarification labels
- [x] `ambiguity_present` derived only from `target_slot_value == '<ambiguous>'`
- [x] Provenance preserved (all 9 source fields verbatim in `source_metadata`)
- [x] Guarded writes only; summary paths repo-relative
- [x] TDD red-green recorded; full suite passes (122 tests)
- [x] Mapping doc contains no raw utterances
- [x] No changes to `data/raw/`, schema, or curated configs
- [x] No benchmark metrics produced

## Row counts / metric outputs

| Metric | Value |
| --- | ---: |
| source_rows_read | 906 |
| rows_converted | 906 |
| rows_skipped | 0 |
| rows_quarantined | 0 |
| rows_ambiguous | 162 |
| rows_concrete_target | 744 |
| output_ids_unique | 906 |

Per split:

| Split | Read | Converted | Ambiguous | Concrete |
| --- | ---: | ---: | ---: | ---: |
| train | 246 | 246 | 44 | 202 |
| validation | 272 | 272 | 42 | 230 |
| test | 388 | 388 | 76 | 312 |

## Evidence and traceability
- Mapping version: `indirect_requests-1.0.0`; schema version: `1.0.0`
- Source shards:
  - train SHA-256 `b4a43371c025b21bdccac460c53c9fd63bb2bf6c588d53b8a2de822eb4c0adc9`
  - validation SHA-256 `3376a4c83fc266f9c62d235855df85d74aac0dedd31b1274ffeca81e22bd01b6`
  - test SHA-256 `ee93197e8a7fed4e139efdedbd59a73118e7deab91e4d397539c70f7d4345456`
- Output: `data/interim/indirect_requests/indirect_requests_canonical.jsonl`
- Quarantine: `data/interim/indirect_requests/indirect_requests_quarantine.jsonl`
- Summary: `outputs/metrics/indirect_requests_conversion_summary.json`
- Mapping doc: `docs/mapping/indirect_requests_mapping.md`

## Unresolved TODO_VERIFY / BLOCKED items
- Licence remains `unresolved` (empty HF metadata; HF card states MIT — not verified on disk).
- Register `mapping_confidence` stays `TODO_VERIFY` per O7 (configs not modified).
- Cross-split repeated `utterance` texts (452) not deduplicated; `(situation, utterance)` pairs do not overlap across splits.
- `mean_world_understanding` preserved in `source_metadata` only; no evaluation use in T04.
- Git commit not performed (per instruction).

## Stage gate
PASS/FAIL: **PASS**

Reason: All T04 acceptance criteria satisfied via TDD; 122/122 tests pass; 906
IndirectRequests rows converted with zero loss and full schema validation; no
fabricated labels; approved corrections A–H enforced; `data/raw`, schema
v1.0.0, and curated configs untouched.
