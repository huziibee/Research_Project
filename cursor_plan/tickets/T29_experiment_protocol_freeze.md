# T29 — Experiment protocol and artifact freeze

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `11_proposal_alignment_contract.md`
- `10_interpretation_evaluation_framework.md`
- `03_dataset_roles_metrics.md`
- `12_core_stretch_policy.md`

## Goal

Hash and freeze every consequential choice before protected execution.

## Preconditions

- T10–T24 and T26–T28 passed.
- T25 status is recorded.

## Required tasks

1. Import and hash the pre-existing T11 research contract; do not formulate the research question for the first time now.
2. Freeze all seven mandatory systems and exact configurations.
3. Freeze the base model, mandatory adapter, prompts, few-shot examples, schemas, decoding, parsers, repair policy, and shared semantic cache.
4. Freeze context-sampling variants/sample count/seeds/uncertainty formula and router thresholds/precedence.
5. Freeze the exact scalar degree baseline and thresholds.
6. Freeze silent-resolution policy IDs, clarification/rejection policies, and safety mock/interface behaviour.
7. Freeze train/dev/test roles, eligibility manifest, metric formulas/denominators, equivalence rules, and critical slots.
8. Freeze cost matrix, statistical tests, alpha/correction, mandatory ablations, and any approved stretch plan.
9. Record T25 official/triage/exploratory status.
10. Create a machine-readable protocol manifest and guard that rejects every mismatch.
11. Create a versioned deviation log and protected-access approval record.

## Deliverables

- Frozen protocol document.
- Machine-readable manifest/hashes.
- Protected guard/tests.
- Deviation/access logs.
- T29 completion report.

## Acceptance criteria

- [ ] All seven systems are named and hashed.
- [ ] Mandatory adapter is frozen.
- [ ] Context-sampling and degree baseline are fully specified.
- [ ] Every official metric and denominator is frozen.
- [ ] The guard rejects altered/missing artifacts and accepts only the frozen set.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after the protocol guard passes. Do not inspect or run protected examples in this ticket.
