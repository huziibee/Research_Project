# T02 — Dataset discovery, row counts, and field audit

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Discover available dataset files, verify row counts, inspect columns, and produce a dataset audit report.

## Why this ticket exists

Planning row counts exist, but Cursor must verify from actual files. No converter may be built from assumed columns.

## Planning row counts to verify

| Dataset | Planned approx rows |
|---|---:|
| AmbiK | 1,400 |
| IndirectRequests | 906 |
| CLARA | 5,345 |
| ClariQ | 15,988 |
| SafeAgentBench | 700 |
| TEACh | 2,280 |
| Dynamic-RDMM | 19,721 |
| RefCOCO | 378,784 |
| ReferIt3D | 323,177 |
| CMC | 1,571 |

Core uploaded datasets expected in `data/raw/` or user-provided paths:

```text
ambik_standardized*.csv
indirect_requests_standardized*.csv
clara_standardized*.csv
clariq_standardized*.csv
safe_agent_bench_standardized*.csv
teach_standardized*.csv
dynamic_rdmm_standardized*.csv
refcoco_standardized*.csv
referit3d_standardized*.csv
cmc_standardized*.csv
```

External candidates not guaranteed present:

```text
CoDraw-iCR v2
VAGUE
```

## Required tasks

1. Locate dataset files.
2. For each found CSV:
   - count rows,
   - list columns,
   - inspect first 3 rows safely,
   - inspect metadata field shape if present,
   - report missing/null counts for key fields: `command`, `scene_context`, `dialogue_history`, `capability_context`, `metadata`.
3. Create `docs/mapping/dataset_audit.md`.
4. Create machine-readable `outputs/metrics/dataset_audit.json`.
5. Mark unavailable datasets as `MISSING_NOT_BLOCKING` unless required by current ticket.

## Deliverables

- `docs/mapping/dataset_audit.md`
- `outputs/metrics/dataset_audit.json`
- Script under `scripts/audit_datasets.py` or package equivalent.
- Tests or smoke validation for audit JSON shape.
- Completion report.

## Acceptance criteria

- Actual row counts are reported from files.
- No dataset is claimed present unless file exists.
- Metadata shapes are summarized without dumping full datasets into chat.
- Missing external CoDraw/VAGUE is clearly noted and does not block uploaded-data work.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after audit report is generated. Do not build converters.

## Additional required audit outputs

Create:

- `docs/decisions/dataset_inclusion_register.md`;
- `docs/dataset_cards/source_licence_manifest.md`;
- file hashes, source versions, and acquisition dates where available;
- exact row counts and unique source-ID counts;
- duplicate and missing-field summaries;
- a clear included/excluded/auxiliary/challenge recommendation for every approved candidate dataset.

No dataset may proceed to final evaluation until its licence and supported labels are documented.
