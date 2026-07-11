# T34 — Robustness challenge suite

**Status:** STRETCH_NONBLOCKING

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `12_core_stretch_policy.md`
- `10_interpretation_evaluation_framework.md`

## Goal

Test the frozen systems on human-verified perturbations and difficult ambiguity combinations.

## Preconditions

- T30 primary experiment is complete.
- T29 robustness policy exists if this ticket proceeds.

## Required tasks

1. Create deterministic or human-reviewed perturbations for paraphrase, spelling/grammar noise, clause order, irrelevant context, contradictory context, missing context, longer compound commands, unseen combinations, and capability changes.
2. Preserve semantic labels where intended and re-annotate any transformation that changes meaning.
3. Keep challenge records separate from confirmatory test metrics.
4. Run frozen systems without tuning and compare clean-versus-perturbed deltas.
5. Optionally include separately documented safety challenge data when licence/mapping permits.
6. Report per-phenomenon failures and eligibility.

## Deliverables

- Challenge set/provenance.
- Clean/perturbed predictions and delta tables.
- T34 completion report.

## Acceptance criteria

- [ ] No unreviewed synthetic label is treated as gold.
- [ ] Challenge results are separately labelled.
- [ ] Systems are not tuned on challenge failures.
- [ ] A truthful nonblocking status is allowed.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after robustness reporting. Do not update frozen systems.
