# Ticket completion report

## Ticket
- ID: T08
- Title: ClariQ optional clarification auxiliary converter

## Preconditions checked
- T00–T07 complete; schema v1.0.0 frozen; ClariQ registered auxiliary in curated
  inclusion register.
- Authoritative source: `data/raw/ClariQ/data/train.tsv` (9,176 rows).
- Approved T08 policy applied: full-row SHA-256 source IDs, Q00001 exclusion,
  exact-duplicate quarantine, conflicting composite preservation, no bank/qrel
  access during conversion.
- `data/raw/` not modified.

## Files created/changed

### Created
- `src/ambiguity_manager/converters/clariq.py`
- `scripts/convert_clariq.py`
- `tests/test_clariq_converter.py`
- `tests/fixtures/clariq/tiny_clariq.tsv`
- `tests/fixtures/clariq/bad_header_clariq.tsv`
- `tests/fixtures/clariq/exact_duplicate_clariq.tsv`
- `tests/fixtures/clariq/conflicting_composite_clariq.tsv`
- `tests/fixtures/clariq/q00001_clariq.tsv`
- `tests/fixtures/clariq/duplicate_q00001_clariq.tsv`
- `tests/fixtures/clariq/inconsistent_cn_clariq.tsv`
- `tests/fixtures/clariq/invalid_ids_clariq.tsv`
- `tests/fixtures/clariq/malformed_width_cn_clariq.tsv`
- `tests/fixtures/clariq/reorder_clariq_a.tsv`
- `tests/fixtures/clariq/reorder_clariq_b.tsv`
- `tests/fixtures/clariq/whitespace_trim_clariq.tsv`
- `docs/mapping/clariq_mapping.md`
- `docs/reports/ticket_T08_completion_report.md`

### Generated (git-ignored data/outputs)
- `data/interim/clariq/clariq_canonical.jsonl`
- `data/interim/clariq/clariq_quarantine.jsonl`
- `data/interim/clariq/clariq_excluded.jsonl`
- `outputs/metrics/clariq_conversion_summary.json`

### Not modified
- `data/raw/**`
- `src/ambiguity_manager/schema/**` (schema v1.0.0 unchanged)
- `configs/datasets/*.json`
- Prior converters and their outputs
- Project split, model, or metric code

## Tests written first, if TDD applies
- Test file: `tests/test_clariq_converter.py`
- Red phase: `PYTHONPATH=src python -m unittest tests.test_clariq_converter -v`
  -> `ModuleNotFoundError: No module named 'ambiguity_manager.converters.clariq'`
  (errors on import). Recorded before implementation.
- Green phase: 19 ClariQ tests pass; full suite **246** tests pass.

## Commands run
- Red: `PYTHONPATH=src python -m unittest tests.test_clariq_converter -v` -> FAILED (ModuleNotFoundError)
- Green (module): `PYTHONPATH=src python -m unittest tests.test_clariq_converter -v` -> OK (19 tests)
- Green (full): `PYTHONPATH=src python -m unittest discover -s tests` -> OK (246 tests)
- Conversion: `PYTHONPATH=src python scripts/convert_clariq.py` -> success
- Independent validation: `read_canonical_jsonl` + `validate_canonical_record` on all 8,565 records -> OK

## Validation results
- 8,565/8,565 output records pass `validate_canonical_record()` on independent reload.
- Unique output IDs: 8,565.
- Accounting invariant holds: `9176 = 8565 + 610 + 1 + 0`.
- Only `data/raw/ClariQ/data/train.tsv` opened for production conversion.
- Canonical output ordering is stable by `topic_id`, `facet_id`, `question_id`, and `full_row_sha256`.
- `authoritative_file_only=true` for the production train.tsv conversion.
- Converter does not open question_bank, qrel, dev, test, or multi-turn files.
- No fabricated route, ambiguity, risk, capability, intent, or slot labels.
- All writes routed through `resolve_writable_path()`; summary paths repo-relative.

## Acceptance criteria status
- [x] ClariQ converted as auxiliary only (`mapping_notes=auxiliary_non_robotic_clarification`)
- [x] Reads only authoritative `train.tsv`
- [x] Converted records pass canonical schema v1.0.0 validation
- [x] Clarification question fields preserved when non-empty
- [x] Full row accounting with duplicate classification evidence
- [x] Q00001 rows excluded by policy with verbatim raw rows in excluded JSONL
- [x] Stable full-row-hash source IDs; conflicting composite rows preserved
- [x] Guarded writes; repo-relative summary paths
- [x] TDD red-green recorded; full suite passes (246 tests)
- [x] Mapping doc contains no raw corpus text
- [x] No changes to `data/raw/`, schema, or curated configs
- [x] No core split assignment or benchmark metrics produced

## Row counts / metric outputs

| Metric | Value |
| --- | ---: |
| source_rows_read | 9176 |
| rows_converted | 8565 |
| rows_excluded_by_policy | 610 |
| rows_quarantined | 1 |
| rows_skipped | 0 |
| raw_q00001_rows | 610 |
| unique_q00001_rows_excluded | 610 |
| output_ids_unique | 8565 |

Duplicate classification:

| Metric | Value |
| --- | ---: |
| composite_collision_groups | 17 |
| rows_in_composite_collision_groups | 34 |
| exact_duplicate_groups | 1 |
| exact_duplicate_rows_beyond_first | 1 |
| conflicting_composite_groups | 16 |
| distinct_rows_in_conflicting_composite_groups | 32 |

Quarantine/exclusion reasons:

| Reason | Count |
| --- | ---: |
| duplicate_exact_row | 1 |
| source_no_question_marker | 610 |

## Evidence and traceability
- Mapping version: `clariq-1.0.0`; schema version: `1.0.0`
- Source SHA-256: `f84245484ab65294f765a76527c6aeea612838b3c4ee51249ab4ae37b1c6161d`
- Output: `data/interim/clariq/clariq_canonical.jsonl`
- Quarantine: `data/interim/clariq/clariq_quarantine.jsonl`
- Excluded: `data/interim/clariq/clariq_excluded.jsonl`
- Summary: `outputs/metrics/clariq_conversion_summary.json`
- Mapping doc: `docs/mapping/clariq_mapping.md`
- Licence remains `unresolved` (no licence file on disk).
- Register `mapping_confidence` stays `TODO_VERIFY` (configs not modified per approval).

## Unresolved TODO_VERIFY / BLOCKED items
- ClariQ licence unresolved.
- Curated register not updated (`mapping_confidence` still `TODO_VERIFY`).
- `dev.tsv` / test splits not converted (deferred).
- qrel document-relevance data not used; detailed qrel counts omitted from T08 deliverables.
- Git commit not performed (per instruction).

## Stage gate
PASS/FAIL: **PASS**

Reason: All T08 acceptance criteria satisfied via TDD; 246/246 tests pass; 8,565
rows converted with 610 policy exclusions and 1 exact-duplicate quarantine;
full schema validation; auxiliary scope enforced; `data/raw`, schema v1.0.0, and
curated configs untouched.
