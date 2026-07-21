# T14 — Blind double annotation, agreement, and adjudication

**Status:** READY
**Active:** no
**Collection started:** no

## Shared context

T00–T11 are completed. T11 ethics/governance determination is `not_required` for supervisor-only annotation (`ETHGOV-001`). T12 is ACTIVE. T13 has not started. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket when activated. Do not access protected test data before T29 passes.

## Required reference documents

- `08_manual_gold_dataset_program.md`
- `10_interpretation_evaluation_framework.md`
- `docs/governance/evidence/ETHGOV-001_supervisor_only_determination.md`
- `docs/protocols/human_annotation_governance.md`

## Goal

Create trustworthy human-adjudicated gold and measure whether the scheme is reproducible.

## Preconditions

- T13 pilot passed. **Not yet satisfied.**
- T11 ethics/governance determination permits supervisor-only collection. **Satisfied as ethics gate; does not start collection.**

## Current readiness

T14 remains blocked on the T13 pilot and unresolved protocol questions: supervisor role separation, independent Annotator A/B assignment when both annotators are project supervisors, and adjudication rules under role overlap. No collection has begun. External annotators remain forbidden without reassessment.

## Required tasks

1. Build blind annotation tooling/views that hide model labels, critiques, and other annotator answers.
2. Run a fresh calibration subset with Annotators A and B independently.
3. Compute raw agreement, categorical kappas, per-label/macro ambiguity kappa, Jaccard/exact-set agreement, CPC/slot agreement, unresolved-slot agreement, risk/capability/route agreement, and prevalence.
4. Apply predefined agreement gates; if failed, revise the handbook and annotate a new calibration subset rather than reusing the failed set as proof.
5. Run full double annotation with immutable annotator IDs and timestamps.
6. Adjudicate disagreements using documented evidence and reason codes.
7. Build final gold schema-v2 records with valid interpretations, intent/CPC, evidence, ambiguity, risk, capability, route, response targets, and resolved slots.
8. Create a separate adjudicated candidate-vs-gold relation subset for optional T25 semantic meta-evaluation.
9. Audit role overlap, missing labels, impossible combinations, and actual counts.

## Deliverables

- Annotation tool/export.
- Agreement reports.
- Adjudication log.
- Final gold records.
- Semantic relation subset.
- Governance/role-overlap audit.
- T14 completion report.

## Acceptance criteria

- [ ] Every gold record is traceable to independent annotations and adjudication.
- [ ] Agreement is reported honestly with prevalence.
- [ ] No model-generated label becomes gold without human verification.
- [ ] CPC and route labels are both present where eligible.
- [ ] Resolved-slot gold exists for silent-resolution cases.

## Test and evidence policy

Do not force unit tests for subjective judgement. Test all validators, import/export logic, counters, and deterministic support scripts.

## Stop condition

Stop after gold build and agreement gate. Do not split or expose protected records.
