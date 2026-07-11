# T13 — Manual-gold guidelines and LLM-assisted scenario authoring

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `08_manual_gold_dataset_program.md`
- `10_interpretation_evaluation_framework.md`
- `03_dataset_roles_metrics.md`

## Goal

Freeze operational annotation rules and create a human-reviewed candidate pool without treating generated labels as gold.

## Preconditions

- T11 governance passed.
- T12 local authoring model exists.
- T10 schema-v2 validators pass.

## Required tasks

1. Write the annotation handbook for speech act, CPC, valid interpretation sets, unique resolvability, unresolved slots, evidence, ambiguity, risk, capability, routes, strategy sequences, clarification targets, rejection reasons, and resolved slots.
2. Define route precedence and borderline/tie-breaking cases.
3. Freeze the benchmark target/minimum and a coverage/design-cell matrix before bulk generation.
4. Create 20–30 human seed scenarios covering clear, single, compound, context-resolved, low/high risk, conditional capability, incapable, and multi-step cases.
5. Implement local LLM generator, critic, adversarial critic, and coverage-check roles through `ModelClient`.
6. Store all generation provenance and keep model-proposed labels/critiques out of blind annotation views.
7. Generate a pilot pool across design cells and run schema, contamination, duplicate, and coverage checks.
8. Perform human author review and retain/edit/reject each scenario with reason codes.
9. Produce annotation-ready records with no official gold labels and actual funnel counts.

## Deliverables

- Annotation handbook and decision tree.
- Design-cell configuration and human seed bank.
- LLM authoring pipeline.
- Pilot candidate pool and provenance.
- Duplicate/coverage/contamination reports.
- Pilot readiness report and T13 completion report.

## Acceptance criteria

- [ ] Every retained scenario is coherent, answerable, and human-reviewed.
- [ ] Generated labels are not exposed as gold.
- [ ] CPC, evidence, valid-set, and resolved-slot semantics are operationally defined.
- [ ] Generated siblings share group IDs.
- [ ] Actual counts replace estimates.

## Test and evidence policy

Do not force unit tests for subjective judgement. Test all validators, import/export logic, counters, and deterministic support scripts.

## Stop condition

Stop after the pilot is approved. Do not conduct full annotation or access protected data.
