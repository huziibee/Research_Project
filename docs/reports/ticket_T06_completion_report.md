# Ticket completion report

## Ticket
- ID: T06
- Title: VAGUE source analysis, label-semantic decision, canonical converter, efficient Parquet reading, validation, and row-accounting evidence

## Preconditions checked
- T00–T05 complete; 155 tests green before T06 work began.
- Authoritative source verified: `data/raw/vague_bench/data/train-00000-of-00001.parquet` (1,677 rows, ~221 MB).
- Approved mapping decisions O1–O17 applied (indirect command, caption scene_context, ambiguity abstention, solution/MCQ gold, image-byte exclusion, image_name IDs).
- Curated configs not modified.

## Files created/changed

### Created
- `src/ambiguity_manager/converters/vague.py`
- `scripts/convert_vague.py`
- `tests/test_vague_converter.py`
- `tests/fixtures/vague/build_fixtures.py`
- `docs/mapping/vague_mapping.md`
- `docs/reports/ticket_T06_completion_report.md`

### Generated (git-ignored data/outputs)
- `data/interim/vague/vague_canonical.jsonl`
- `data/interim/vague/vague_quarantine.jsonl` (empty; 0 quarantined)
- `outputs/metrics/vague_conversion_summary.json`

### Not modified
- `data/raw/**`
- `src/ambiguity_manager/schema/**` (schema v1.0.0 unchanged)
- `configs/datasets/*.json`
- Prior converters and their outputs
- Model, routing, split-generation, or metric code

## Tests written first, if TDD applies
- Test file: `tests/test_vague_converter.py`
- Red phase: `PYTHONPATH=src python -m unittest tests.test_vague_converter -v`
  -> `ModuleNotFoundError: No module named 'ambiguity_manager.converters.vague'`
  (errors=1). Recorded before implementation.
- Green phase: 27 new VAGUE tests pass; full suite **193** tests pass after hardening.

## Commands run
- Red: `PYTHONPATH=src python -m unittest tests.test_vague_converter -v` -> FAILED (errors=1)
- Green (module): `PYTHONPATH=src python -m unittest tests.test_vague_converter -v` -> OK (27 tests)
- Green (full): `PYTHONPATH=src python -m unittest discover -s tests` -> OK (193 tests)
- Conversion: `PYTHONPATH=src python scripts/convert_vague.py` -> success
- Independent validation: reloaded and re-validated all 1,677 output records

## Validation results
- 1,677/1,677 output records pass `validate_canonical_record()` on independent reload.
- Unique output IDs: 1,677; unique `source_id` (`image_name`): 1,677.
- Every record has exactly 4 `candidate_interpretations`.
- `ambiguity_present` is `null` on every record; no fabricated route/risk/capability labels.
- `label_eligibility.intent_slots=true` and `context_benefit=true` on all 1,677 records.
- `image` column excluded from Parquet projection; `image_bytes_read=false` in summary.
- No `image`, `image_path`, or binary payloads in `source_metadata` (0 hits on 1,677 records).
- Accounting invariant holds: `1677 = 1677 + 0 + 0`.
- Quarantine file empty.

## Acceptance criteria status
- [x] VAGUE payload present; no blocked missing-data path
- [x] Reads only authoritative Parquet shard; never reads `.cache`
- [x] `ParquetFile` with projected columns and row-group iteration
- [x] Schema validated before conversion
- [x] Full row accounting with reasons
- [x] No silent row loss; unique output IDs
- [x] All output records pass canonical schema v1.0.0 validation
- [x] Candidate/gold interpretation preserved
- [x] No fabricated route, risk, capability, or ambiguity-taxonomy labels
- [x] No image bytes in JSONL or `source_metadata`
- [x] Visual-context assumptions documented in mapping doc
- [x] Guarded writes; repo-relative summary paths
- [x] TDD red-green recorded; full suite passes (182 tests)
- [x] Mapping doc contains no raw utterances
- [x] No changes to `data/raw/`, schema, or curated configs
- [x] No benchmark metrics produced

## Row counts / metric outputs

| Metric | Value |
| --- | ---: |
| source_rows_read | 1677 |
| rows_converted | 1677 |
| rows_quarantined | 0 |
| rows_skipped | 0 |
| output_ids_unique | 1677 |
| unique_source_ids | 1677 |
| candidate_interpretations_per_record | 4 |

Per subcorpus (converted):

| Subcorpus | Count |
| --- | ---: |
| vcr (`@` in image_name) | 1144 |
| ego4d | 533 |

Quarantine reasons: none.

## Evidence and traceability
- Mapping version: `vague-1.0.0`; schema version: `1.0.0`
- Source SHA-256: `cf3a9a7655d32ac030c35210bbaad33634327dea3bf1669bf59b0dde5adc1e44`
- Output: `data/interim/vague/vague_canonical.jsonl`
- Quarantine: `data/interim/vague/vague_quarantine.jsonl`
- Summary: `outputs/metrics/vague_conversion_summary.json`
- Mapping doc: `docs/mapping/vague_mapping.md`
- Projected columns: `image_name`, `direct`, `indirect`, `solution`, `mcq`, `meta` (no `image`)

## Hardening (post-review)

- `validate_parquet_schema()` now validates exact nested `mcq` and `meta` child types.
- Per-row `mcq.ordering` validated as a permutation of `{A,B,C,D}`; invalid rows
  quarantine as `invalid_mcq_ordering`.
- 11 additional tests for schema rejection and ordering validation.
- Licence remains `unresolved` (no licence file on disk).
- Register `mapping_confidence` stays `TODO_VERIFY` (configs not modified per approval).
- Project ambiguity taxonomy mapping deferred (abstained by approved policy).
- Route / clarification-decision labels remain unsupported.
- Git commit not performed (per instruction).

## Stage gate
PASS/FAIL: **PASS**

Reason: All T06 acceptance criteria satisfied via TDD; 193/193 tests pass; 1,677
VAGUE rows converted with zero loss and full schema validation; no image bytes
read or serialized; no fabricated labels; `data/raw`, schema v1.0.0, and curated
configs untouched.
