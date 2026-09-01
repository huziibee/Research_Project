# T35 — Repeated-run and route-stability analysis

**Status:** STRETCH_NONBLOCKING — stochastic stability is not applicable to
the current frozen greedy decoder; T39 owns execution-reproducibility checks.

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `12_core_stretch_policy.md`

## Goal

Measure stochastic variability and safety-critical route flips only when a
separate frozen stochastic-decoding protocol exists. The current Pilot-120
evaluator uses `do_sample=False`: five T39 replays therefore test byte/output
reproducibility, not independent stochastic performance.

## Preconditions

- T30 primary predictions exist.
- T29 seed/repetition policy exists if proceeding.

## Required tasks

1. Do not introduce sampling, temperatures, or seeds into the current Pilot.
2. Confirm greedy replay-content hashes remain identical. Preserve raw
   prediction-file SHA-256 for artifact integrity, but do not treat finite
   numeric wall-clock `latency_ms` differences as model-output drift; any
   replay-content, raw-integrity, or execution-contract drift requires runtime
   investigation.
3. Do not report mean, standard deviation, or confidence summaries over
   byte-identical reruns as statistical performance variability.
4. Measure per-example interpretation agreement, route agreement, and safety-critical flips.
5. Trace unstable cases to raw outputs and context-sampling features.
6. Do not choose the best seed as the official result.

## Deliverables

- Repeated-run manifests/predictions.
- Stability tables and unstable-case list.
- T35 completion report.

## Acceptance criteria

- [ ] Decoding/settings are frozen and remain greedy.
- [ ] Deterministic drift is treated as a defect.
- [ ] Safety-critical flips are explicit.
- [ ] A truthful nonblocking status is allowed.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after stability analysis. Do not alter decoding or routing.
