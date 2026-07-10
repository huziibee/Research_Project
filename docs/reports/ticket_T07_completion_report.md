# Ticket completion report

## Ticket
- ID: T07
- Title: CLARA/SaGC source analysis, label-semantic decision, canonical converter, route abstention or mapping policy, validation, and row-accounting evidence

## Preconditions checked
- T00–T06 complete; 193 tests green before T07 work began.
- Authoritative source verified: `data/raw/CLARA-Dataset/data/agument.json` (5,345 rows).
- Approved label mapping policy O1–O3 applied (labels 0–2 converted; label 3 excluded;
  label 2 route/rejection abstention; robot-type-only `capability_context`).
- Curated configs not modified.

## Files created/changed

### Created
- `src/ambiguity_manager/converters/clara.py`
- `scripts/convert_clara.py`
- `tests/test_clara_converter.py`
- `tests/fixtures/clara/tiny_clara.json`
- `tests/fixtures/clara/invalid_source_id.json`
- `tests/fixtures/clara/missing_goal.json`
- `tests/fixtures/clara/unknown_label.json`
- `tests/fixtures/clara/unknown_task.json`
- `tests/fixtures/clara/duplicate_top_level_key.json`
- `docs/mapping/clara_mapping.md`
- `docs/reports/ticket_T07_completion_report.md`

### Generated (git-ignored data/outputs)
- `data/interim/clara/clara_canonical.jsonl`
- `data/interim/clara/clara_quarantine.jsonl` (empty; 0 quarantined)
- `data/interim/clara/clara_excluded.jsonl` (123 rows)
- `outputs/metrics/clara_conversion_summary.json`

### Not modified
- `data/raw/**`
- `src/ambiguity_manager/schema/**` (schema v1.0.0 unchanged)
- `configs/datasets/*.json`
- Prior converters and their outputs
- Model, routing, split-generation, or metric code

## Tests written first, if TDD applies
- Test file: `tests/test_clara_converter.py`
- Red phase: `PYTHONPATH=src python -m unittest tests.test_clara_converter -v`
  -> `ModuleNotFoundError: No module named 'ambiguity_manager.converters.clara'`
  (errors=1). Recorded before implementation.
- Green phase: 23 new CLARA tests pass; full suite **216** tests pass.

## Commands run
- Red: `PYTHONPATH=src python -m unittest tests.test_clara_converter -v` -> FAILED (errors=1)
- Green (module): `PYTHONPATH=src python -m unittest tests.test_clara_converter -v` -> OK (23 tests)
- Green (full): `PYTHONPATH=src python -m unittest discover -s tests` -> OK (216 tests)
- Conversion: `PYTHONPATH=src python scripts/convert_clara.py` -> success
- Independent validation: reloaded and re-validated all 5,222 canonical records

## Validation results
- 5,222/5,222 output records pass `validate_canonical_record()` on independent reload.
- Unique output IDs: 5,222; unique `source_id`: 5,222.
- Accounting invariant holds: `5345 = 5222 + 123 + 0 + 0`.
- Per-label converted: 0=1749, 1=1560, 2=1913; excluded label 3=123.
- Label 2 records: `recommended_strategy=null`, `capability_status=unknown`,
  `label_eligibility.routing=false`, `label_eligibility.rejection=false`.
- No fabricated ambiguity subtypes or risk labels on any record.
- `capability_context` contains robot type only (no permitted-action lists).
- `scene_context` is deterministic sorted JSON of source scene.
- Quarantine file empty.

## Acceptance criteria status
- [x] CLARA label semantics verified from local README, notebook, and paper text
- [x] Converter reads only authoritative `agument.json`
- [x] Full row accounting with per-label breakdown and exclusion reasons
- [x] No silent row loss; unique output IDs; deterministic ordering
- [x] All converted records pass canonical schema v1.0.0 validation
- [x] Approved label mappings for 0/1/2; label 3 excluded by policy
- [x] Label 2 route and rejection abstained; capability unknown
- [x] No fabricated ambiguity taxonomy, risk, clarification, or slots
- [x] Guarded writes; repo-relative summary paths
- [x] TDD red-green recorded; full suite passes (216 tests)
- [x] Mapping doc contains no raw utterances
- [x] No changes to `data/raw/`, schema, or curated configs
- [x] No benchmark metrics produced

## Row counts / metric outputs

| Metric | Value |
| --- | ---: |
| source_rows_read | 5345 |
| rows_converted | 5222 |
| rows_excluded_by_policy | 123 |
| rows_quarantined | 0 |
| rows_skipped | 0 |
| output_ids_unique | 5222 |

Per label (converted):

| Label | Count |
| --- | ---: |
| 0 | 1749 |
| 1 | 1560 |
| 2 | 1913 |

Excluded:

| Label | Count | Reason |
| --- | ---: | --- |
| 3 | 123 | source_label_3_semantic_conflict |

## Evidence and traceability
- Mapping version: `clara-1.0.0`; schema version: `1.0.0`
- Source SHA-256: `f7be73a71a5e5651264fe15dbce4881d727d096e5d322ff2e0081c58de220350`
- Output: `data/interim/clara/clara_canonical.jsonl`
- Quarantine: `data/interim/clara/clara_quarantine.jsonl`
- Excluded: `data/interim/clara/clara_excluded.jsonl`
- Summary: `outputs/metrics/clara_conversion_summary.json`
- Mapping doc: `docs/mapping/clara_mapping.md`
- Licence remains `unresolved` (no licence file on disk).
- Register `mapping_confidence` stays `TODO_VERIFY` (configs not modified per approval).
- Git commit not performed (per instruction).

## Unresolved TODO_VERIFY / BLOCKED items
- Curated `configs/datasets/dataset_inclusion_register.json` not updated (`mapping_confidence` still `TODO_VERIFY`).
- CLARA licence unresolved.
- Label 3 semantic conflict documented; 123 rows excluded pending any future relabel decision.
- Ambiguity taxonomy mapping intentionally abstained.

## Hardening (post-review)

- Raw `goal` and `task` preserved verbatim in `source_metadata`; canonical
  `command` and `capability_context` use trimmed validated values.
- Strict source typing: string `goal`/`task`, `type(label) is int` (booleans rejected),
  scene exactly `{floorplan, objects, people}` with string list items.
- Source IDs: whitespace trim, leading-zero rejection, normalized decimal form,
  duplicate normalized IDs raise `ClaraConversionError`.
- CLI prints `summary['summary_path']` (repo-relative).

## Stage gate
PASS/FAIL: **PASS**

Reason: All T07 acceptance criteria satisfied via TDD; 216/216 tests pass; 5,222
CLARA rows converted with 123 policy exclusions and zero quarantine; full schema
validation; no fabricated labels; `data/raw`, schema v1.0.0, and curated configs
untouched.
