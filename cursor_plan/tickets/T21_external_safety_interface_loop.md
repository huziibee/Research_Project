# T21 — External safety-interface loop

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `11_proposal_alignment_contract.md`

## Goal

Test downstream safety feedback integration without replacing the manager’s own risk and capability classification.

## Preconditions

- T19 internal risk/capability predictions exist.
- T20 selected/resolved interpretations exist.

## Required tasks

1. Define a provider-neutral safety interface returning `allow`, `reject`, or `needs_disambiguation` with reason/provenance.
2. Implement deterministic mock fixtures and failure/timeout behaviour.
3. Submit each candidate interpretation independently and retain all responses.
4. Define how safety feedback updates route decisions while preserving the original internal risk/capability prediction for analysis.
5. Handle all rejected, mixed, multiple-allowed, and needs-disambiguation cases.
6. Add tests proving the safety interface does not silently overwrite internal labels.
7. Record the component as an integration mock, not a claim of complete safety classification.

## Deliverables

- Safety interface and mocks.
- Integration policy/tests.
- Dev traces.
- T21 completion report.

## Acceptance criteria

- [ ] Internal risk/capability prediction remains visible.
- [ ] Every candidate has traceable safety feedback.
- [ ] Timeout/failure defaults are conservative and explicit.
- [ ] No full safety-classifier claim is made.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after the integration loop passes fixtures. Do not generate user-facing responses.
