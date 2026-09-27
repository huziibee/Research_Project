# Base vs fine-tuned adapter — does fine-tuning help?

Date: 2026-09-11. Uses frozen evidence only. Adapter remains unofficial /
provisional.

## Short answer

**On the Pilot-120 routing task that matters for your early report: no.**
The unofficial adapter is slightly worse than the base model on route-correct
(87/120 vs 88/120), and that gap is identical on all five T39 replicas.

Fine-tuning **does** help some other T28 source-dev metrics (schema validity /
some routing subsets), but it never cleared the official selection bar, and on
one important ambiguity-detection slice it was worse than base.

## 1. Pilot-120 (frozen T39) — headline for the supervisor

Terminal route accuracy, n=120, five GPU replicas:

| Replica | Direct base (Qwen3-8B) | Early Pilot adapter | Delta |
|---|---:|---:|---:|
| R1 | 88/120 (0.733) | 87/120 (0.725) | −1 |
| R2 | 88/120 | 87/120 | −1 |
| R3 | 88/120 | 87/120 | −1 |
| R4 | 88/120 | 87/120 | −1 |
| R5 | 88/120 | 87/120 | −1 |

So the fine-tune is **reproducibly not better** on Pilot routing.

Per-class (R1):

| Route | Base recall | Adapter recall | Note |
|---|---:|---:|---|
| execute | 0.658 | 0.711 | Adapter executes a bit more |
| clarify | 0.739 | 0.739 | Same |
| refuse | 1.000 | 0.762 | Adapter misses more refusals |

That tradeoff matters: the adapter gains some execute recall and loses refuse
recall. Overall accuracy still favours base.

## 2. T28 source-dev (why people thought fine-tuning “worked”)

From `handover/09_08_2026/T28_HANDOVER.md`:

**R6 full candidate** (`t28-tc-full-v1-1500`, the early Pilot package ancestor):

- `adapter_beats_base: true` on the **contract-compatible routing subset** (n=296)
- But `adapter_eligible_for_selection: false`
- Reason: only 190/296 full safe assemblies; many `predict_interpretations_v1` failures (`no_json` / digit loops)
- Adapter full safe assemblies 190 vs base 6 — better JSON discipline on some tasks, not a clean win

**Nuclear recovery track** (technical smoke only):

- Schema-valid overall: adapter 1.000 vs base ~0.989
- But on `ambiguity_present` True calls: adapter ~174 vs base ~712 — **failed** the “beat base to promote” bar

## 3. How to say this in the report

Honest one-liner:

> Fine-tuning did not improve Pilot-120 routing over the base Qwen3-8B. The
> unofficial adapter is 87/120 vs base 88/120 across five replicas. On source-dev
> diagnostics the adapter sometimes beats base on subset routing / schema
> emission, but it never became selection-eligible, and on ambiguity-present
> recovery one candidate underperformed the base.

Do **not** claim “the fine-tuned manager is the reason for good results.”
The strong Pilot story is goal understanding + over-asking of the **manager
policy**, not adapter superiority.

## 4. What this implies for v2 / goal-first

Goal-first v2 is mostly a **prompt + router** change on the same base+adapter
stack. If v2 wins, credit the new analysis/routing contract, not “SFT fixed it.”
If base alone is used later as an ablation, expect routing near the 88/120 band
unless the new prompt changes behaviour.

## 5. Goal understanding (new evidence, 11 Sep 2026)

Official SGC was never scored on base vs adapter. An exploratory goal-trace
proxy using the official SGC cleaner finds **base 68/120 vs adapter 60/120**
(threshold 0.18; McNemar p≈0.24). Mean overlap is nearly identical; adapter has
more polarity conflicts. Details:
`docs/reports/BASE_VS_ADAPTER_GOAL_UNDERSTANDING_20260911.md`.

Do **not** claim the adapter improves goal understanding.
