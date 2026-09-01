# T41 — Interpretation-quality gold and scoring

**Status:** APPROVED_POST_GATE_PROTOCOL_AND_EXECUTION

Create a versioned sidecar gold and frozen output-measurement contract for
intent, CPC, candidates, resolution, clarification/rejection targets and
wording, and silent resolution. Two annotators are blinded to system identity
and each other; per-field agreement/adjudication and immutable hashes are
required. No Pilot-120 field, model, manager, prompt, decoder, threshold or
selection decision changes. Systems without a required output are
`NOT_COMPUTED`, not terminal-route proxies.

**Acceptance:** audited sidecar/schema/review artifacts; field-level metrics;
claim-to-gold coverage table; exact job/artifact hashes; no selection/tuning use.
