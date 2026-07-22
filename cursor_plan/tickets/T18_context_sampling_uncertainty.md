# T18 — Context-sampling uncertainty and output-variance scoring

**Status:** READY
**foundation_status:** SYNTHETIC_VALIDATION_COMPLETE
**official_execution_status:** BLOCKED

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `11_proposal_alignment_contract.md`
- `04_hardware_model_strategy.md`

## Goal

Implement the proposal-required model-agnostic uncertainty feature using controlled context sampling.

## Preconditions

- T17 structured candidate generation exists.
- T15 dev data is available.

## Required tasks

1. Define only semantically controlled context variants: command-only, leave-one-noncritical-context-item-out, order-preserving context masks, and approved context subsets. Do not invent or alter facts.
2. Predefine sample count, seeds, and failure handling.
3. Run the same command across variants and collect candidate frames, ambiguity labels, critical slots, and provisional route signals.
4. Implement output-variance features including candidate-set disagreement, ambiguity-set disagreement, critical-slot instability, route entropy/disagreement, and invalid-output rate.
5. Combine features into a bounded uncertainty score using train/dev-only calibration.
6. Preserve every sampled input/output and explain which context item changed.
7. Test invariance on clear/stable cases and elevated uncertainty on deliberately unresolved cases.
8. Expose the score and components to T19 and the scalar degree baseline, without exposing ambiguity-type semantics to the latter.

## Deliverables

- Context-variant generator.
- Variance/uncertainty module and config.
- Dev calibration report.
- Raw sampled outputs.
- T18 completion report.

## Acceptance criteria

- [ ] Variants do not change underlying facts.
- [ ] Scores are reproducible under frozen seeds.
- [ ] Invalid calls contribute transparently.
- [ ] Thresholds use dev only.
- [ ] The component is real and ablatable, not a placeholder.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after uncertainty outputs and dev calibration exist. Do not route protected examples.
