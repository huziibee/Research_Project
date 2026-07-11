# T10 — Canonical schema v2 and completed-output migration

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `11_proposal_alignment_contract.md`
- `10_interpretation_evaluation_framework.md`

## Goal

Resolve the completed T01 schema conflicts without rerunning T00–T09, then migrate their artifacts into one authoritative schema v2.

## Preconditions

- T00–T09 artifacts and completion reports exist.
- Original T00–T09 files will remain immutable.

## Required tasks

1. Audit the actual T01 implementation, converter outputs, weak pool, fixtures, and every enum/field currently used.
2. Write an Architecture Decision Record declaring schema v2 authoritative for all unfinished work.
3. Freeze `risk_level = none|low|medium|high|unknown` and `capability_status = capable|conditional|incapable|unknown`.
4. Define canonical `unresolved_slots`, structured candidate/selected interpretation frames, CPC fields, supporting evidence, context-sampling uncertainty, route/sequence, clarification/rejection fields, and silent-resolution fields.
5. Define nullability separately for predictions and missing/ineligible gold.
6. Implement schema versioning, validators, invariants, JSONL helpers, and a deterministic v1-to-v2 migration layer.
7. Migrate completed converter and weak-pool outputs to new versioned paths without overwriting originals or rerunning converters.
8. Create compatibility/count reports proving every input row is accounted for and recording unmappable fields.
9. Add tests for enums, nullability, multi-step constraints, selected-interpretation evidence, and silent-resolution invariants.

## Deliverables

- Schema-v2 ADR and JSON Schema/Pydantic definitions.
- Migration code and tests.
- Versioned migrated outputs.
- Input/output/skipped/unmappable reconciliation report.
- T10 completion report.

## Acceptance criteria

- [ ] No T00–T09 converter or builder was rerun.
- [ ] All legacy schema conflicts are resolved by one authority.
- [ ] Every completed row is accounted for.
- [ ] Original artifacts are unchanged.
- [ ] New validators reject legacy ambiguity rather than silently coercing it.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after schema v2 and migrated artifacts pass reconciliation. Do not begin model or annotation work.
