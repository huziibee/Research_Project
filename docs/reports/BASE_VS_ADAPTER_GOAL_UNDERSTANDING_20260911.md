# Base vs adapter — goal-understanding evidence (11 Sep 2026)

## Short answer

On an exploratory **goal-trace proxy** that reuses the official SGC cleaning pipeline, the adapter does **not** beat the base. Base is ahead (68 vs 60 / 120 at the primary threshold). This is **not** official two-judge SGC.

Official Pilot SGC (~113/120) was only scored for manager systems, never for `direct_base_llm` vs the provisional adapter. Those two systems emit no `intent_summary`.

## Method (honest boundary)

1. Same gold-independent cleaners as the intent-eval pack (`clean_observable_trace`, `extract_intent_candidate_text`).
2. Compare cleaned intent excerpts to the two pre-T39 gold `intent_text` references via content-word Jaccard + polarity conflict check.
3. Primary pass threshold: overlap ≥ 0.18, nonempty excerpt, no polarity flip.
4. Route accuracy reported only as context (already frozen: 88 vs 87).

Artifacts:

- `scripts/score_base_vs_adapter_goal_trace_proxy_20260911.py`
- `outputs/base_vs_adapter_goal_trace_proxy_20260911.json`
- `outputs/base_vs_adapter_goal_trace_proxy_rows_20260911.jsonl`

## Primary results (threshold 0.18)

| Metric | Direct base | Provisional adapter |
|---|---:|---:|
| Proxy goal-correct | **68/120** (0.567) | 60/120 (0.500) |
| Mean gold overlap | 0.192 | 0.193 |
| Polarity conflicts | 4 | 10 |
| Empty excerpts | 0 | 0 |
| Route-correct (context) | 88/120 | 87/120 |
| Adapter-only proxy wins | — | 14 |
| Base-only proxy wins | 22 | — |
| McNemar exact p | 0.24 (not significant) | |

Same direction at thresholds 0.12 and 0.25: base ≥ adapter.

## What you may claim

> On Pilot-120 R1, a lexical/polarity goal-trace proxy using the official SGC cleaner does not show the unofficial adapter beating the base (68 vs 60 / 120). Mean overlap is nearly identical; the adapter has more polarity conflicts. This is not official SGC.

## What you must not claim

- “Official SGC says adapter understands goals better/worse”
- That this proxy replaces the two-blind-judge protocol

## To finish official SGC later

Build a base/adapter blind packet with `build_intent_eval_packet.py` logic pointed at:

- `review_bundles/.../R1/direct_base/direct_base_llm.predictions.jsonl`
- `review_bundles/.../R1/selected_adapter/t28_selected_adapter_llm.predictions.jsonl`

Then run two independent judges. Do **not** start that GPU work while 53074/53081 own the queue unless supervisors ask.
