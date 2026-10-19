# Compound ambiguity grounding: implementation and exploratory results

**Date:** 19 October 2026  
**Project:** huziibee/Research_Project, experimental branch only  
**Scope:** natural-language instruction + textual context to an action-ready
structured task, not motion planning, robot safety, or authorization gating.

## What was built and verified

1. **Task-graph model:** ordered multi-action templates with explicit arguments,
   cross-action references, alternative guarded graphs, arithmetic values,
   and dependent lookups. Complete candidate tasks, not individual words, are
   compared for semantic action identity. The current equivalence is strict
   structural JSON equality and still needs semantic canonicalisation.
2. **Global grounding and readiness:** finite candidate assignments are
   evaluated consistently; a unique complete-task interpretation is
   provisionally `action_ready`, multiple different tasks imply clarification,
   and invalid or excessive candidates cause abstention. Candidate coverage
   is explicitly NOT validated; the engine cannot establish uniqueness beyond
   hypotheses actually supplied by the semantic model.
3. **Interactive clarification:** a transparent partition heuristic picks a
   variable that best distinguishes the remaining candidate tasks under an
   uncalibrated uniform assignment assumption; a response fixes that variable
   and re-evaluates all task dependencies. Responses are currently exact
   option values rather than general unrestricted natural language.
4. **Evidence checks:** verbatim quotes are matched against input text.
   Exact substring support does not prove semantic support or candidate recall.
5. **Source-only Qwen integration:** schema prompt, injectable model interface,
   optional pinned Qwen3-8B loader, resumable 120-case source-only runner,
   validation and failure recording. The pinned Qwen checkpoint was NOT run
   during this local development session.
6. **Tests:** 42 deterministic unit tests passed on ten ChatGPT-authored,
   gold-visible Pilot-120 examples plus one synthetic dependency example.

## Three distinct evidence tracks (DO NOT combine into one accuracy claim)

| Evidence track | N | Measured result | What it means |
|---|---:|---|---|
| Manual ChatGPT TaskSpecs + deterministic graph engine | 10 Pilot + 1 synthetic | Targeted tests pass | Mechanism works on manually prepared interpretations; no blind parsing measurement |
| Gold-visible archival candidate sets | 120 | 97 one-candidate ready, 23 two-candidate clarify; all 23 respond to either candidate choice | An oracle-input consistency check, tautological with respect to source candidate count; not model performance |
| Raw source-only lexical readiness probe | 99 E/C | 89/99 = 89.9% | Exploratory pattern matching; NOT task-graph correctness |
| Raw source lexical probe + archived refusal gate | 120 | 106/120 = 88.3% | Exploratory first-turn three-way agreement, NOT full action readiness |

Comparison baselines on the same frozen 120: old capability-repaired
Goal-First 83/120 (69.2%); always-ready-behind-gate 93/120 (77.5%);
Raw Qwen direct routing 96/120 (80.0%). These scores represent different
systems and are not clean claims of improvement. The 120 cases have been
examined repeatedly during development; the lexical probe is highly sensitive
to explicit verbal markers in those scene descriptions.

### Exact source-only probe confusion

Gold rows and predicted columns EXECUTE / CLARIFY / REFUSE:

```
EXECUTE   72   0   4
CLARIFY    8  13   2
REFUSE     0   0  21
```

Without the separate historical refusal gate, the readiness cohort of 99
cases is 76/76 gold EXECUTE treated as ready candidate and 13/23 gold CLARIFY
recognized as blocking ambiguity. **Ten true clarification needs are missed**.
Six old refusal mistakes remain untouched by the gate-preserving hybrid:
four EXECUTE->REFUSE and two CLARIFY->REFUSE.

### Remaining 14 hybrid errors and mechanisms

- **Gold EXECUTE -> REFUSE (4):** CA-0042, CA-0203, CA-0259, CA-0369.
  These are inherited capability/permission refusals; outside the current
  ambiguity verifier's scope.
- **Gold CLARIFY -> REFUSE (2):** CA-0552, CA-0727. Destination-unit
  alternatives remain unresolved, but the historical gate refuses them.
- **Gold CLARIFY -> EXECUTE (8):** CA-0056 and CA-0092 (two selected items),
  CA-0078 (two recipients for one role), CA-0070, CA-0714 and CA-0786
  (unselected return/storage unit), CA-0671 and CA-0845
  (missing range-dependent instrument choice).

Each of these unresolved cases is an opportunity for explicit scene candidate
extraction, joint grounding and a targeted question. The current lexical
probe is deliberately NOT retrospectively tuned to these IDs. Testing on a
new independent set is essential before interpreting improved counts.

## Research papers: method -> component -> motivation

| Paper | Mechanism used | Implementation area | Important non-equivalence |
|---|---|---|---|
| CLARA, Park et al. (2024), DOI:10.1109/LRA.2023.3338514 | Keep clear instructions apart from ones that need asking, use contextual questions | `pipeline.run_dialogue`, `engine.resolve` | No CLARA model weights or training process were reproduced |
| AmbiK, Ivanova et al. (ACL 2025), DOI:10.18653/v1/2025.acl-long.1593 | Candidate interpretations and contextually resolved vs unresolved examples | `examples/*.json`, `engine._candidate_bindings` | Gold-visible development examples, not new AmbiK training |
| Global Grounding in Flexible Robot Tasks with Object Number Variety, Sucker & Henrich (2025), DOI:10.1109/LRA.2025.3560864 | Globally consistent assignment of referents across related operations | `$lookup`, shared variables, full-graph comparison | A small finite Python constraint enumerator, not their original grounding algorithm |
| Instruction Clarification Requests in Multimodal Collaborative Dialogue Games, Madureira & Schlangen (EACL 2023), DOI:10.18653/v1/2023.eacl-main.169 | Distinguish *when* to ask from quality/utility of the question | `engine._partition_score`, separate question feedback | No new CoDraw-iCR-trained clarification model |
| ClarifyVC, Zhou et al. (ICLR 2026), https://openreview.net/forum?id=afO3vnSNsS | Persistent grounding over multiple clarification turns and ambiguous-command testing | `pipeline.run_dialogue`, `apply_answer`, 5-turn cap | Not their hybrid data augmentation pipeline |
| KnowNo, Ren et al. (CoRL 2023), https://proceedings.mlr.press/v229/ren23a.html | Preserve alternative actions and ask when uncertainty remains | `engine.resolve` and candidate-set recording | NO conformal prediction or calibrated coverage guarantee |
| Bayesian Active Learning for Intent Disambiguation in Interactive Robot Planning (2026), https://www.huao-li.com/bal/ | Questions should distinguish full candidate tasks, reducing residual uncertainty | `engine._partition_score` | Only uniform partition heuristic; NO Bayesian learner or task planner |
| v35 Goal-First and Qwen3 Technical Report (2025), arXiv:2505.09388 | Preserve complete requested job and required action set before downstream grounding | `model_adapter.build_model_prompt`, `qwen_adapter` | Actual model inference has NOT been run in this version |

### Central hypothesis for a new held-out experiment

Jointly grounding candidate **complete task graphs** and clarifying only the
remaining action-changing alternatives should improve exact task correctness
and reduce unnecessary clarification relative to direct routing or independent
slot grounding, especially for *dependent compound ambiguity*. This is a
research hypothesis, **not a validated result of the present development set**.

## Outstanding work

**Blocking for an end-to-end claim:** run a real source-only model on all 120,
produce syntactically valid complete task graphs, independently verify candidate
coverage and grounding support, and compare graph correctness against
independently adjudicated annotations. Add a genuinely unseen evaluation set
before model selection or reporting confirmatory performance.

Other future work: natural-language answer interpretation, semantic
canonicalisation of equivalent action graphs, constraints over entities not
explicitly listed by the model, perception and real robot execution if desired.

## Reproducibility and preservation

Keep every original v35 and Pilot-120 file immutable. New scripts live under
`research/prototypes/compound_task_grounding_v02/`. Never pass gold, original
route, previous predictions or capability/risk labels into `run_qwen120.py`.
Saved aggregate results are under `results/pilot120_source_probe_v02/`.
The interpretation-key oracle smoke requires the separately preserved
`pilot120_interpretation_key_candidate_v2.jsonl`; it must never be substituted
for raw model input in a claimed blinded experiment. Upstream source rights
remain governed by the parent repository's rights register.