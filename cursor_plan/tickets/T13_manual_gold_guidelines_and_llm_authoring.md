# T13 — Manual-gold guidelines, calibration packages, and authoring programme

**Status:** ACTIVE (preparation / calibration freeze)
**Active:** yes (foundation and calibration; main package not frozen)
**Collection started:** no

## Shared context

T00–T12 are completed. T11 ethics/governance determination is `not_required` for
supervisor-only annotation (`ETHGOV-001`). T12 closed with
`technical_stack_status=PASS`, `terminal_candidate_outcome=candidate_rejected`,
and `selected_model=null`. Follow `01_global_cursor_contract.md`,
`02_context_refresh_protocol.md`, and `DEC-20260722-001`.

## Required reference documents

- `08_manual_gold_dataset_program.md`
- `10_interpretation_evaluation_framework.md`
- `03_dataset_roles_metrics.md`
- `docs/governance/evidence/ETHGOV-001_supervisor_only_determination.md`
- `docs/protocols/annotation_handbook_v1.md`
- `docs/protocols/annotation_role_policy_v1.md`
- `docs/decisions/DEC-20260722-001_t13_parallel_execution_order.md`

## Goal

Freeze operational annotation rules and create an annotation-ready programme with
a reviewed calibration package. Do **not** treat generated or authored labels as
official gold. Do **not** freeze the final 300-record main package in the initial
foundation delivery.

## Preconditions

- T11 governance passed (PASS; determination `not_required`; supervisor-only). **Satisfied.**
- T12 closed (stack PASS; candidate may be rejected; `selected_model` may remain null). **Satisfied.**
- T10 schema-v2 validators pass. **Satisfied.**
- **`selected_model` is not a T13 prerequisite.**

## Roles

| Role | Person | Pseudonym |
|---|---|---|
| Dataset author / reviewer | Mohammed Bangie | `AUTHOR-01` |
| Official Annotator A | Steven James | `ANN-A` |
| Official Annotator B | Benjamin Rosman | `ANN-B` |
| Adjudicator | unresolved until T14 | `ADJ-01` |

Mohammed must not be assigned as `ANN-A` or `ANN-B`.

## Dataset size policy

- Calibration: **24** records (refine handbook/interface; not automatic gold).
- Main target: **300** adjudicated records.
- Optional expansion toward **400** only after coverage audit and supervisor workload review.
- Local-LLM authoring is **optional future tooling**, not required for T13 acceptance.

## Required tasks

1. Amend roadmap/ticket text for parallel execution (`DEC-20260722-001`).
2. Freeze annotation handbook, role policy, taxonomies, and annotation schema.
3. Implement deterministic candidate/package tooling (IDs, duplicates, contamination, coverage, manifests).
4. Author and freeze the 24-record calibration package with independent ANN-A/ANN-B views.
5. Prepare main-pool authoring templates and remaining-count tooling without freezing 300 records.
6. Support T14A synthetic tooling foundations in the same delivery window.
7. Produce foundation/calibration reports.

## Deliverables

- Annotation handbook and role policy.
- Machine-readable taxonomies, schema, design cells, and roles.
- Annotation package module and CLI.
- Calibration source + ANN-A/ANN-B packages, manifests, hashes, reports.
- Main-pool authoring readiness artefacts (templates/queue; no main freeze).
- T13 foundation and calibration report.

## Acceptance criteria

- [ ] Handbook and schema are frozen and versioned.
- [ ] Roles enforce Mohammed ≠ ANN-A/ANN-B; only supervisors annotate officially.
- [ ] Calibration has exactly 24 reviewed records with required coverage.
- [ ] ANN-A and ANN-B packages share IDs, hide hidden fields, and contain no gold.
- [ ] Duplicate/contamination/coverage tooling is deterministic and CPU-only.
- [ ] Main 300 package is not frozen in this ticket stage.
- [ ] No official gold labels; no real supervisor annotation started.

## Test and evidence policy

Test validators, package builders, hashing, role policy, coverage, contamination,
and deterministic support scripts. Do not force unit tests for subjective
judgement quality of scenarios beyond structural coverage gates.

## Stop condition

Stop after calibration packages and tooling are ready for supervisor review.
Do not start T14B human annotation. Do not freeze the main 300 package. Do not
access protected data.
