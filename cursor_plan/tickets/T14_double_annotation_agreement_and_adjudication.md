# T14 — Blind double annotation, agreement, and adjudication

**Status:** READY (T14A tooling may proceed; T14B/T14C pending)
**Active:** no (human collection not started)
**Collection started:** no

## Shared context

T00–T12 are completed. T11 ethics/governance determination is `not_required` for
supervisor-only annotation (`ETHGOV-001`). T13 foundation and calibration may be
in progress or frozen for review. Follow `01_global_cursor_contract.md`,
`02_context_refresh_protocol.md`, and `DEC-20260722-001`.

## Required reference documents

- `08_manual_gold_dataset_program.md`
- `10_interpretation_evaluation_framework.md`
- `docs/governance/evidence/ETHGOV-001_supervisor_only_determination.md`
- `docs/protocols/human_annotation_governance.md`
- `docs/protocols/annotation_handbook_v1.md`
- `docs/protocols/annotation_role_policy_v1.md`

## Goal

Create trustworthy human-adjudicated gold and measure whether the scheme is
reproducible. Split delivery:

### T14A — tooling (may proceed before real annotation)

Immutable package loading, independent A/B storage, validation, progress,
blindness guards, agreement metrics, disagreement reports, adjudication queue,
and gated gold export. Develop and test with **synthetic** submissions only.

### T14B — human annotation (pending)

Requires T13 calibration (and later main) package freeze, accepted handbook,
role policy, and supervisor availability. Official annotators are Steven James
(`ANN-A`) and Benjamin Rosman (`ANN-B`) only.

### T14C — adjudication (pending)

Requires both completed annotation sets. Retain originals; unresolved
adjudicator identity (`ADJ-01`) until policy approval. No single annotation
silently becomes gold.

## Preconditions

- T13 handbook/schema/role policy exist. **Required for T14A completeness.**
- T13 calibration package frozen before T14B calibration annotation.
- T11 ethics/governance permits supervisor-only collection. **Satisfied as ethics gate; does not start collection.**

## Current readiness

T14B/T14C remain blocked on supervisor availability, calibration review, and
adjudication-role resolution. External annotators remain forbidden without
reassessment. Do not mark human annotation as started when only T14A tooling
exists.

## Required tasks

1. Build blind annotation tooling/views that hide model labels, critiques, and other annotator answers.
2. Support synthetic and later real independent A/B submissions.
3. Compute raw agreement, categorical kappas, multi-label Jaccard, CPC/slot agreement, and prevalence.
4. Apply predefined agreement gates on calibration before main annotation.
5. Run full double annotation with immutable annotator IDs and timestamps (T14B).
6. Adjudicate disagreements using documented evidence and reason codes (T14C).
7. Build final gold schema-v2 records only after adjudication.
8. Audit role overlap, missing labels, impossible combinations, and actual counts.

## Deliverables

- Annotation tool/export foundations (T14A).
- Agreement reports.
- Adjudication log.
- Final gold records (after T14C only).
- Governance/role-overlap audit.
- T14 completion report (after T14B/T14C).

## Acceptance criteria

- [ ] Every gold record is traceable to independent annotations and adjudication.
- [ ] Agreement is reported honestly with prevalence.
- [ ] No model-generated label becomes gold without human verification.
- [ ] CPC and route labels are both present where eligible.
- [ ] Raw A/B submissions remain immutable.
- [ ] Gold export refuses incomplete/unresolved adjudication.

## Test and evidence policy

Test all validators, import/export logic, counters, agreement metrics, and
deterministic support scripts with synthetic fixtures. Do not force unit tests
for subjective judgement.

## Stop condition

T14A may stop after synthetic readiness. T14B/T14C stop after gold build and
agreement gate. Do not split or expose protected records. Do not claim human
annotation started based on tooling alone.
