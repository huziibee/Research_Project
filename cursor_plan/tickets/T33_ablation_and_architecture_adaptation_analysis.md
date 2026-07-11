# T33 — Ablation and architecture-versus-adaptation analysis

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `04_hardware_model_strategy.md`
- `11_proposal_alignment_contract.md`

## Goal

Measure which components matter and separate routing-architecture gains from fine-tuning gains.

## Preconditions

- T29 ablations are frozen.
- T30 primary runs are complete.

## Required tasks

1. Run frozen component ablations: no risk, no capability, no ambiguity types, no context, no multi-step, no context-sampling uncertainty, and no deterministic router.
2. Run the mandatory 2x2 comparison: direct+base, manager+base/no adapter, direct+adapter/no manager routing, and manager+adapter.
3. Hold the base model, eligible records, decoding, and input access constant where the condition permits.
4. Measure intent/CPC, candidate, ambiguity, risk/capability, route, unsafe behaviour, and cost changes.
5. Use paired statistical comparisons against the full manager.
6. Mark metrics not applicable rather than fabricating values.
7. Retain null or adverse ablation results.

## Deliverables

- Ablation configs/predictions.
- 2x2 architecture/adaptation table.
- Metric/cost/statistical comparisons.
- T33 completion report.

## Acceptance criteria

- [ ] One intended factor changes per component ablation where possible.
- [ ] Architecture and adapter effects are separately observable.
- [ ] Same-base fairness is preserved.
- [ ] Interpretation and route effects are separate.
- [ ] No redesign occurs after results.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after ablation analysis. Do not create improved post-test variants.
