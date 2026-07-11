# T23 — Seven mandatory comparison systems

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `11_proposal_alignment_contract.md`
- `12_core_stretch_policy.md`
- `04_hardware_model_strategy.md`

## Goal

Integrate and smoke-test all seven mandatory systems under a shared schema and controlled comparison design.

## Preconditions

- T16–T22 passed.

## Required tasks

1. Implement `always_execute`, `always_clarify`, and `always_silently_resolve` using the cached shared base semantic analysis so the route policy—not a different parser—is the main change.
2. Define always-execute and always-silent commitment behaviour explicitly; preserve unsupported-commitment failures for scoring.
3. Retain `direct_base_llm` from T16.
4. Implement `degree_based_router` using only a scalar ambiguity/severity score and context-sampling variance; it must not access ambiguity type, risk, capability, or type-specific precedence.
5. Freeze the degree score range and dev-selected thresholds mapping to execute/silently_resolve/clarify. It does not emit rejection or multi-step routes.
6. Implement `context_blind_manager` as the full manager architecture with scene, dialogue, and capability context removed; it later uses the same fine-tuned adapter as the full manager.
7. Integrate `full_finetuned_type_risk_manager` architecture provisionally with the base model; T28 supplies the mandatory adapter before final freeze.
8. Ensure every system outputs schema v2, raw/parsed records, route, interpretation, and applicability flags.
9. Run non-test smoke fixtures and compare interfaces, not final results.

## Deliverables

- Seven system implementations/configs.
- Exact degree-baseline specification.
- Shared semantic cache policy.
- Smoke predictions and interface report.
- T23 completion report.

## Acceptance criteria

- [ ] All seven systems exist and run on the same fixtures.
- [ ] No system is marked optional.
- [ ] Degree-based routing cannot access type/risk/capability semantics.
- [ ] Context-blind inputs are demonstrably stripped.
- [ ] The full manager is clearly awaiting the required T28 adapter.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after seven-system smoke tests. Do not run protected data or claim final results.
