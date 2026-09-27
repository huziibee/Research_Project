# Project completion ticket plan — 2026-09-11

## Non-negotiable boundaries

T39 and T41 are frozen. Dataset-native results are exploratory weak-source-label studies, not replacements for official T29–T38 or T42 evidence. Do not tune a system, threshold, prompt, or label after full-run results are read.

## Lane 1 — early report package (active)

| Work | Ticket relationship | Exit evidence |
|---|---|---|
| VAGUE goal recovery/context ablation | T06, T33 diagnostic extension | hash-bound full outputs, paired score, error ledger |
| AmbiK ambiguity type | T03, T19 diagnostic extension | full outputs, exact-set score, weak-label boundary |
| CLARA context/routing | T07, T18–T20 diagnostic extension | full/ablated outputs, paired score |
| Indirect Requests pragmatic recovery | T04, T19 diagnostic extension | full outputs, source-mapped score |
| early supervisor package | T31–T33/T36–T38 reporting analogue | manifest, hashes, results tables, limitations |

Promotion gate: canary schema/coverage/fingerprint/manifest pass. Full-result freeze precedes all error analysis.

## Lane 2 — official evidence closure

1. T13–T15: human-guideline, double-blind annotation/adjudication, protected split/eligibility evidence.
2. T16–T24: system and deterministic evaluator completion; preserve the original no-LLM-official-judge rule.
3. T27–T28: select an adapter only if eligibility is proven; otherwise issue formal no-adapter decision.
4. T29–T38: frozen execution, statistics, ablations, failure analysis, reproducibility audit.
5. T39–T41: retain closure; do not rerun.
6. T42: new independent source, two blind reviews + adjudication, and three-way no-overlap ledger. Current status blocked by missing source/annotations/T41–T44 ledgers.
7. T43/T44/T45: factorial context, independent-family confirmation, and historical reconciliation.

## Critical ablation questions

- Does textual scene context improve VAGUE goal-triplet recovery within records?
- Does CLARA context change ambiguity/capability/strategy recovery within records?
- Does goal recovery survive speech-act/route errors in frozen T39? Report only observable traces.
- Which errors first appear at goal, speech-act, structured grounding, or route layers? Mark unavailable layers `NOT_COMPUTED`.

Critical pre-result review: `docs/reports/CRITICAL_ABLATION_REVIEW_20260911.md` records the current evidence boundary, identifiable contrasts, confounds, and reporting gates. It is a review document, not a change to frozen artifacts or scoring criteria.

## Improvement backlog after each result freeze

1. Enforce JSON-schema decoding at first generation; retry is transport-only.
2. Preflight every cluster node/container GPU before queueing models.
3. Human-audit mapped weak labels before making stronger claims.
4. Add a separately versioned `intent_summary` output contract; never alter T39. Implemented as `goal_first_manager_v2` — see `docs/reports/GOAL_FIRST_V2_FIX_LIST_20260911.md`; submit with `cluster/goal_first_v2/submit.sh`.
5. Add CoDraw/ClariQ blind semantic review, not lexical/LLM self-scoring.
6. Turn recurring error clusters into preregistered T42 strata, never post-hoc tuning targets.
7. Treat CLARA as a 3-class template recovery (strategy determines ambiguity and capability); run a 2×2 scene×capability factorial rather than another composite blind arm.
8. Report Indirect Requests against the 82.1% majority baseline, unique-input n=452, and positive-class recall.
9. For VAGUE, split caption gains by whether the gold object string is literally in the caption; command-only exact-triplet copy is bounded at 1/1677.
10. Do not infer environment task success from route correctness. Future `FutureTaskOutcomeV2` is required before any “wrong turn, right result” execution claim.
