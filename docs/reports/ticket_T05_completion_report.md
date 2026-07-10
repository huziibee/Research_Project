# Ticket completion report

## Ticket
- ID: T05
- Title: CoDraw-iCR v2 source analysis, clarification semantics, canonical converter, grouping and row-accounting evidence

## Preconditions checked
- T00–T04 complete; 124 tests green before T05 work began.
- Authoritative source verified: `data/raw/codraw-icr-v2/codraw-icr-v2.tsv` (8,765 rows).
- Auxiliary `codraw-icr-v2_raw.tsv` confirmed present but excluded from conversion.
- Approved mapping decisions §1–17 applied (instruction anchoring, ambiguity abstention,
  no `teller_after` leakage, weak-mapped record policy, eligibility flags).
- Curated configs not modified.

## Files created/changed

### Created
- `src/ambiguity_manager/converters/codraw_icr_v2.py`
- `scripts/convert_codraw_icr_v2.py`
- `tests/test_codraw_icr_v2_converter.py`
- `tests/fixtures/codraw_icr_v2/tiny_codraw.tsv`
- `tests/fixtures/codraw_icr_v2/bad_header_codraw.tsv`
- `tests/fixtures/codraw_icr_v2/malformed_codraw.tsv`
- `tests/fixtures/codraw_icr_v2/anchor_edge_codraw.tsv`
- `tests/fixtures/codraw_icr_v2/quarantine_codraw.tsv`
- `tests/fixtures/codraw_icr_v2/dup_id_codraw.tsv`
- `tests/fixtures/codraw_icr_v2/non_icr_codraw.tsv`
- `tests/fixtures/codraw_icr_v2/unknown_mood_codraw.tsv`
- `docs/mapping/codraw_icr_v2_mapping.md`
- `docs/reports/ticket_T05_completion_report.md`

### Generated (git-ignored data/outputs)
- `data/interim/codraw_icr_v2/codraw_icr_v2_canonical.jsonl`
- `data/interim/codraw_icr_v2/codraw_icr_v2_quarantine.jsonl`
- `outputs/metrics/codraw_icr_v2_conversion_summary.json`

### Not modified
- `data/raw/**`
- `src/ambiguity_manager/schema/**` (schema v1.0.0 unchanged)
- `configs/datasets/*.json`
- Prior converters (AmbiK, IndirectRequests) and their outputs
- Model, routing, split-generation, or metric code

## Tests written first, if TDD applies
- Test file: `tests/test_codraw_icr_v2_converter.py`
- Red phase: `PYTHONPATH=src python -m unittest tests.test_codraw_icr_v2_converter -v`
  -> `ModuleNotFoundError: No module named 'ambiguity_manager.converters.codraw_icr_v2'`
  (errors=1). Recorded in `outputs/metrics/_t05_red.txt`.
- Green phase: 27 new CoDraw-iCR v2 tests pass; full suite **151** tests pass.

## Commands run
- Red: `PYTHONPATH=src python -m unittest tests.test_codraw_icr_v2_converter -v` -> FAILED (errors=1)
- Green (module): `PYTHONPATH=src python -m unittest tests.test_codraw_icr_v2_converter -v` -> OK (27 tests)
- Green (full): `PYTHONPATH=src python -m unittest discover -s tests` -> OK (151 tests)
- Conversion: `PYTHONPATH=src python scripts/convert_codraw_icr_v2.py` -> success
- Independent validation: reloaded and re-validated all 7,034 output records

## Validation results
- 7,034/7,034 output records pass `validate_canonical_record()` on independent reload.
- Unique output IDs: 7,034.
- `ambiguity_present` is `null` on every record; `resolved_interpretation` is `null` on every record.
- `label_eligibility.clarification_decision` and `context_benefit` are `false` on every record.
- `label_eligibility.clarification_target` is `true` on every converted record.
- Accounting invariant holds: `8765 = 7034 + 1731 + 0`.
- No use of `codraw-icr-v2_raw.tsv`.

## Acceptance criteria status
- [x] Reads only authoritative `codraw-icr-v2.tsv`
- [x] Full row accounting with honest converted/quarantine counts
- [x] Instruction anchoring: `command=teller_before` only when `is_source=1`
- [x] `teller_after` never used in canonical fields
- [x] Ambiguity fields abstain; content flags preserved in `source_metadata`
- [x] `scene_context=null`; no synthesized scene text
- [x] `resolved_interpretation=null` on all records
- [x] `gold_clarification_question=drawer`; mood normalization for `clarification_subtype`
- [x] `weak_mapped` / `weak_derived` with approved eligibility flags
- [x] CoDraw split prefix preserved (`train` / `validation` / `test`)
- [x] Every converted record passes canonical schema v1.0.0 validation
- [x] Guarded writes only; summary paths repo-relative
- [x] TDD red-green recorded; full suite passes (151 tests)
- [x] Mapping doc contains no raw utterances
- [x] No changes to `data/raw/`, schema, or curated configs
- [x] No benchmark metrics produced

## Row counts / metric outputs

| Metric | Value |
| --- | ---: |
| source_rows_read | 8765 |
| rows_converted | 7034 |
| rows_quarantined | 1731 |
| rows_skipped | 0 |
| output_ids_unique | 7034 |

Quarantine reasons:

| Reason | Count |
| --- | ---: |
| source_instruction_unavailable | 1730 |
| missing_command | 1 |

Per split (converted):

| Split | Converted |
| --- | ---: |
| train | 5604 |
| validation | 726 |
| test | 704 |

Clarification subtype counts (top):

| Subtype | Count |
| --- | ---: |
| polar question | 2363 |
| wh- question | 2013 |
| alternative question | 1248 |
| other | 326 |
| declarative | 177 |

(Full distribution in `outputs/metrics/codraw_icr_v2_conversion_summary.json`.)

## Evidence and traceability
- Mapping version: `codraw_icr_v2-1.0.0`; schema version: `1.0.0`
- Source SHA-256: `2ef3981fa67cb8a16e9ba3165053046a38fbc29ed71aadd5a9d5c1033ea009bf`
- Output: `data/interim/codraw_icr_v2/codraw_icr_v2_canonical.jsonl`
- Quarantine: `data/interim/codraw_icr_v2/codraw_icr_v2_quarantine.jsonl`
- Summary: `outputs/metrics/codraw_icr_v2_conversion_summary.json`
- Mapping doc: `docs/mapping/codraw_icr_v2_mapping.md`

## Unresolved TODO_VERIFY / BLOCKED items
- Licence remains `stated_unverified` (CC BY-NC 4.0 stated in README; `license.txt` not on disk).
- Register `mapping_confidence` stays `TODO_VERIFY` (configs not modified).
- 1,731 rows quarantined because source instruction is unavailable under approved
  anchoring policy (primarily `is_source_utterance_last_turn != 1`).
- Clarification-decision and context-benefit metrics remain ineligible (`false`).
- Ambiguity-type mapping from content flags deferred.
- Git commit not performed (per instruction).

## Stage gate
PASS/FAIL: **PASS**

Reason: All T05 acceptance criteria satisfied via TDD; 151/151 tests pass; 7,034
rows converted with full accounting (7,034 + 1,731 = 8,765); no fabricated
labels or `teller_after` leakage; `data/raw`, schema v1.0.0, and curated configs
untouched.
