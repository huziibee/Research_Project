# T41 — Interpretation-quality gold and scoring

**Status:** CPU_READINESS_VERIFIED; POST-GATE HUMAN STUDY NOT QUEUED; RESULTS NOT COMPUTED

Create a versioned sidecar gold and frozen output-measurement contract for
intent, CPC, candidates, resolution, clarification/rejection targets and
wording, and silent resolution. Two annotators are blinded to system identity
and each other; per-field agreement/adjudication and immutable hashes are
required. No Pilot-120 field, model, manager, prompt, decoder, threshold or
selection decision changes. Systems without a required output are
`NOT_COMPUTED`, not terminal-route proxies.

Where T39's deterministic error taxonomy needs a semantic claim rather than a
saved-field rule, the same two blinded annotators independently code the
pre-registered taxonomy record set and reconcile disagreements. Until that
artifact exists, the taxonomy's human-double-coding status remains
`NOT_COMPUTED`; deterministic cross-checks are not relabelled as human review.

**Acceptance:** audited sidecar/schema/review artifacts; field-level metrics;
claim-to-gold coverage table; exact job/artifact hashes; no selection/tuning use.

## CPU-only readiness record (2026-09-01)

`configs/evaluation/t41_interpretation_sidecar_contract_v1.json` and
`scripts/pilot120_t41_interpretation_readiness.py` now validate the required
sidecar, blind-review and adjudication fields without writing a label or
calling a model. The readiness report has status
`T41_READINESS_CONTRACT_PASSED` for the frozen contract only; it is not an
interpretation result. The score contract explicitly makes every missing gold
target or required system field `NOT_COMPUTED`, never a terminal-route proxy.

The next work remains independent licensed source material where needed, two
blinded reviews, adjudication, a frozen fixed-system output contract and a
separate scorer. No human annotation, T41 metric or cluster job is complete.
