# Proposed Table III — compound task manager comparisons (unmeasured template)

**Never fill prospective task-graph or success@5 fields using historical route scores or the post-hoc 114/120 source-only probe.** New results require identical data, schema, evaluation and answer protocol.

## Primary paper table

| System | Intent correct | E/C macro-F1 @0 | False-ready C->E | Exact full task @0 | Dependency edge F1 | Correct complete task @5 | Mean useful questions | E2E latency p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Raw Qwen3-8B (same input, direct) | — | — | — | — | — | — | — | — |
| **Full Manager Qwen3-8B** | — | — | — | — | — | — | — | — |
| Context-Blind Qwen3-8B (no scene/dialogue evidence) | — | — | — | — | — | — | — | — |
| Manager minus Goal-First intent recovery | — | — | — | — | — | — | — | — |
| Manager minus structured compound task graph | — | — | — | — | — | — | — | — |
| Manager minus ambiguity candidate discovery | — | — | — | — | — | — | — | — |
| Manager minus joint contextual grounding | — | — | — | — | — | — | — | — |
| Manager minus task-equivalence readiness verification | — | — | — | — | — | — | — | — |
| Manager minus targeted question selection | — | — | — | — | — | — | — | — |
| Manager minus persistent clarification state | — | — | — | — | — | — | — | — |
| Manager Qwen3-4B | — | — | — | — | — | — | — | — |
| Manager Qwen3-1.7B | — | — | — | — | — | — | — | — |

## Secondary metrics to include in Results / Appendix

- Action-node F1; action argument micro-F1; exact critical argument frame; scope and coreference accuracy.
- Ambiguity variable F1; gold task candidate-set coverage; hallucinated/unsupported candidate rate.
- First-turn EXECUTE/CLARIFY confusion, abstentions, parse failures, over-clarification, no-answer counts.
- Success@d for d=0,1,2,3,4,5; conditional on cases actually needing clarification as well as all action-eligible cases. Missing answers, depth caps, unsupported ready states count as failures for correct-complete-task success.
- Compound complexity strata: one action versus multi-action; number of **blocking** ambiguity variables; independent versus dependency-linked ambiguity; alternative action graphs/negation scope.
- Per-case wins/ties/regressions against raw Qwen and context-blind; judge separately and blind to system name.
- Latency: p50/p95 initial inference, p50/p95 full interaction to correct completion, per-turn output tokens, number of model calls, VRAM; keep hardware, batch size, precision, decoding and constraints fixed.

## Historical comparators: DIFFERENT protocol, display separately

| Prior study stream | Historical routing /120 | Prior two-judge semantic intent /120 |
|---|---:|---:|
| Raw Qwen3-8B | 96 | 106 |
| Goal-First Qwen3-8B (old router) | 56 | 117 |
| Context-Blind Qwen3-8B | 21 | 119 |
| Goal-First after independent capability patch | 83 | Inherited Goal-First interpretation |
| v0.3 lexical source-only + historical refusal gate | 114 | NOT_MODEL_INFERENCE |

Only v35 first-turn routes can be compared within the original scoring setup. The planned Table III evaluates NEW complete-task and five-turn outcomes on a new matched protocol. The 114/120 Pilot-120 source-probe result is a post-hoc diagnostic rather than an independent learned-system result.

## Ablation fairness

- Same source records, random seeds, prompt/output budget, model checkpoint and task schema.
- Remove a component by replacing it with a concrete minimal alternative (e.g. independent local grounding instead of joint grounding), not by starving the system of all usable input.
- Direct Qwen gets the full raw source and an equivalent final output contract. Blind withholds full contextual fields, with correct ablated cache identity.
- For depth five, question-answer oracle returns **only the requested detail** from independently validated ground truth; every system receives the same answer policy and maximum of five real Q+A steps.
- Report both completeness and question count. A system that asks unnecessarily to gain extra information loses on efficiency, even if it eventually produces the correct graph.
- Prespecify tests before final held-out inference. Pilot-120 already informed v0.3 development.
