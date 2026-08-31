# T38 — Final experiment completeness and integrity audit

**Status:** EARLY_AUDIT_PASSED_NON_OFFICIAL; OFFICIAL_CLOSURE_BLOCKED

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `12_core_stretch_policy.md`
- `11_proposal_alignment_contract.md`

## Goal

Issue the final PASS/FAIL/BLOCKED decision for the complete core experiment and separately report stretch status.

## Early-artifact boundary and T39 relationship

The existing `T38_EARLY_INTEGRITY_AUDIT_COMPLETE` artifact passed its stated
120-record hash/denominator/non-tuning checks. It explicitly does not close
official T28 completion, full-1,000 evaluation, model/adapter selection, or
training/tuning. T39 reproducibility evidence is likewise non-official; it can
strengthen early-report traceability but cannot upgrade this ticket's official
status.

## Preconditions

- All applicable T10–T37 completion reports exist.

## Required tasks

1. Audit schema-v2 authority and migration/reconciliation of T00–T09 outputs.
2. Audit research contract, AI-use log, ethics determination, dataset/model licences, and deviations.
3. Audit gold interpretation/CPC/valid-set/resolved-slot quality, agreement, adjudication, leakage, splits, and eligibility.
4. Audit the selected base model, mandatory adapter, and all seven system configs.
5. Audit context-sampling uncertainty, exact degree baseline, route precedence, silent-resolution values, and safety-interface boundaries.
6. Audit T24 formula fixtures and T25 status.
7. Audit T29 hashes/access controls and T30 immutable run matrix/results.
8. Audit cost, statistics, ablations, failure analysis, report artifacts, and per-cell traceability.
9. Record T34/T35 stretch statuses without allowing them to hide core failures.
10. List every TODO_VERIFY, BLOCKED, NOT_COMPUTED, deviation, limitation, and missing artifact.
11. Issue per-area and global `PASS`, `FAIL`, or `BLOCKED`; use `NOT_APPLICABLE` only for approved stretch items.

## Deliverables

- Machine-readable audit.
- Final integrity report.
- Missing-evidence/deviation list.
- Core global status and stretch-status appendix.
- T38 completion report.

## Acceptance criteria

- [ ] Global PASS requires every core area to pass.
- [ ] All seven systems and mandatory adapter are present.
- [ ] Protected-test integrity is demonstrable.
- [ ] Interpretation/CPC and route correctness are fully audited.
- [ ] Dataset restrictions are enforced in code.
- [ ] AI/ethics/licence records are complete.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after the audit. The research report may claim completion only if the core global status is PASS.
