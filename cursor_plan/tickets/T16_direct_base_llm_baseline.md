# T16 — Direct local base-LLM structured baseline

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `04_hardware_model_strategy.md`
- `10_interpretation_evaluation_framework.md`

## Goal

Implement the direct base-model comparator that predicts complete schema-v2 output in one constrained call without the explicit manager pipeline.

## Preconditions

- T12 selected base model exists.
- T15 train/dev data and eligibility exist.

## Required tasks

1. Define the direct structured prompt and JSON schema for intent/CPC, candidates, ambiguity, risk, capability, uncertainty fields, route, response, and resolved slots.
2. Use only train/dev examples for prompt/few-shot design.
3. Implement raw-output preservation, parsing, validation, bounded repair, and explicit failure records.
4. Run development smoke/evaluation only; measure validity, missing critical fields, latency, and deterministic metrics where eligible.
5. Freeze a candidate direct prompt/config for later T29 protocol selection.
6. Expose reusable cached semantic outputs for uniform routing baselines without allowing them to alter the direct prediction.

## Deliverables

- Direct baseline implementation/config.
- Raw/parsed dev predictions.
- Invalid/repair report.
- Candidate prompt decision.
- T16 completion report.

## Acceptance criteria

- [ ] No explicit deterministic manager routing is used.
- [ ] Base model/revision matches the future manager base.
- [ ] No protected records are accessed.
- [ ] Every failure is retained.
- [ ] Schema-v2 output is complete enough for downstream comparisons.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after the direct baseline is stable on dev. Do not implement manager components.
