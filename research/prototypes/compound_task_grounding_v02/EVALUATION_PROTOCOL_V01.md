# Compound Ambiguity Manager — evaluation protocol v0.1

**Status:** PROPOSED prospective protocol, 2026-10-19; not an executed model comparison. Does not amend the Pilot-120 frozen gold, prior predictions or v35. Pilot-120 has informed development and is therefore a diagnostic/development panel; it is **not** an untouched test for the new architecture.

## 1. Objective and task boundary

Input: utterance, dialogue history, textual scene, optional task conventions. Output: a complete, grounded, ordered action graph, OR a targeted clarification question (and persistent state), OR an explicitly unresolved abstention. Capability/authorization is evaluated separately from **semantic action readiness**.

Architecture (all stages must be independently inspectable):
1. Goal and action recovery
2. Structured task graph
3. Compound ambiguity discovery
4. Joint contextual grounding
5. Task-equivalence readiness verification
6. Targeted clarification plus state update, **up to five question-answer turns**
7. Final task compiler and validation

A multi-step job can be action-ready; the requirement is one unambiguous *complete task*, not one atomic action.

## 2. Reuse versus additional annotation

**Existing frozen historical gold** (120): 76 EXECUTE, 23 CLARIFY, 21 REFUSE; ambiguity labels, CPC normalization evidence, route status, some clarification target/wording criteria, and historical pre-T39 candidate interpretations. Keep files unchanged. The *separate* historical candidate-key sidecar contains 97 one-candidate and 23 two-candidate cases. These are **reference candidates created with label knowledge**, not predictions or an independent assessment of candidate completeness.

Detailed sidecar annotation statuses inspected 2026-10-19:
- 95/120 CPC records: `NEEDS_BLIND_ADJUDICATION`; 25: `DUAL_SEMANTIC_CONSENSUS_NORMALIZED`.
- 22/23 clarification records: `TRIANGULATED`; CA-0394 needs blind revalidation.
- The historical gold is a dual-LLM / adjudication pilot, not final-protocol human task-graph gold.

**New independent task_gold_v1 layer:** prefill from historical source, sidecar, existing grounded facts, and previously published annotations. Have two independent annotators read the *source only* and label the complete action graph, all action-critical arguments, cross-action referent identity, partial order and negation/conditions; unresolved variable domains; context-resolved values and provenance; dependency edges; minimal distinguishing clarification questions; and one or more answer-specific terminal task graphs. Adjudicate disagreements blind to system names/predictions. Label unresolved/unsupported facts as unknown, not guessed. Human expert review can resolve ambiguous adjudication; do not silently promote machine-generated annotations to independent gold.

**All 120** require a structured-target validation if one wishes to report `complete_task_exact@0` on all 120, but this is a **verification / schema-conversion pass**, not fresh collection from scratch. Prioritize 23 required-clarify cases (including CA-0394), 95 low-confidence CPC records, and 21 historical refuses for readiness-independent annotation. Original route labels are not replacements for readiness on the 21 refusal records.

**New never-before-inspected held-out set:** independently collect/split by source scenario family; near-duplicate check and freeze hash before model choices. Include at least four strata (unambiguous, single blocking ambiguity, multiple independent ambiguities, *dependent* compound ambiguities), and some naturally requiring 2–5 separate questions. Report provenance of naturally sourced vs deliberately constructed cases. Pilot-120 results are developmental, even if newly annotated.

## 3. Metrics and precise denominators

| Metric | Definition | Report on |
|---|---|---|
| First-turn E/C accuracy and macro-F1 | `EXECUTE/CLARIFY` equivalence of explicit task-ready/needs-clarification decision to reference; failures and abstentions counted wrong | Historical 99 E/C first; new adjudicated readiness across broader data |
| False-ready rate (critical) | Gold needs clarification but predicted ready: `C -> E / N_C` | 23 Pilot-120 clarify, plus new heldout |
| Over-clarification rate | Gold ready but predicted clarify: `E -> C / N_E` | 76 Pilot-120 execute, plus new heldout |
| Semantic intent accuracy | Blind two-judge intended goal agreement (historical exploratory); updated full-action human gold for new analysis | 120 historical / new blinded set |
| Action-graph exact match | Canonical action types, arguments, polarity, partial order and dependencies all correct; no missing required actions | Gold complete tasks; do not substitute fluent intent prose |
| Action-node/edge precision, recall, F1 | Action node matches, precedence/condition/coreference edges after graph canonicalization | New structured gold |
| Action-critical grounding | Grounded argument micro/macro F1 and exact complete argument frame | New structured gold; validate all critical slots |
| Ambiguity-variable P/R/F1 | Action-changing unresolved variables and scopes, not all linguistic ambiguities | New structured gold |
| Compound dependency edge P/R/F1 | Correct cross-variable, cross-action dependency relationships | Dependent-compound stratum |
| Candidate equivalence-class coverage | Gold materially distinct task interpretations represented among model candidates; count invalid unsupported candidates | New structured gold with gold candidate witnesses |
| Clarification target and wording | Question targets gold missing information and meets source-based must-convey / must-not-convey criteria; separately log naturalness | Existing 23 targets and new annotations |
| Question utility | Whether answer eliminates expected gold-equivalence classes without requesting an irrelevant parameter | New interactive labels |
| Correct-complete-task success@d | By at most **d** actual Q+A pairs, final emitted action graph exactly matches gold and all blockers resolved; `d=0..5` | Answered-interaction subset and all E/C in fixed protocol |
| Mean/median turns to valid completion | Include failures at cap separately; do not credit premature false-ready terminal state | Answered-interaction cohort |
| Unnecessary clarification turns | Questions asked after a task was already objectively ready | All appropriately annotated cases |
| Evidence faithfulness | Reference quotes point to source *and* actually support selected binding; substring-only matching is diagnostic | New independent evidence audit |
| Reliability | Invalid-schema generation, model error, unsupported ready, abstention, looping/repeated question, depth-cap counts | All systems, failures in denominator |
| Efficiency | E2E p50/p95 wall time, p50/p95 time to correctly ready, generation tokens per turn, total tokens/job, peak GPU VRAM | Same hardware, prompts, limits, precision, seeds |

**Important:** route agreement is not full task correctness. Also report route-correct/task-wrong and route-wrong/task-correct separately.

## 4. Five-turn interaction contract

At `d=0`: freeze model's interpretation and explicit alternatives, ground against scene and dialogue, and either emit task, ask a question, or abstain. From `d=1` to `d=5`:
1. Select a **specific** unresolved variable/edge/scope with competing action-changing task alternatives.
2. Generate one question (and answer choices where appropriate). Persist action graph, candidate set, constraints, evidence and question target.
3. The user / evaluation answer oracle provides **only the information the question requested**, not the full reference intent; no gold labels or prediction verdicts may enter model prompts.
4. Parse the answer into a typed binding; verify against evidence; update only the affected variables; propagate dependencies and re-evaluate globally.
5. Compile when a single supported, complete task-equivalence class remains. At five asked+answered questions without a correct complete task: `unresolved_at_depth_5` (failure for success@5).
6. Stop early on successful completion; unanswered/invalid answer is logged, not silently replaced with reference intent.
7. Keep a matched **no-answer control with equal re-inference opportunities** if evaluating whether answers causally help, unlike the historical unequal rerun control.

First-turn-only `run_qwen120_v03.py` is **NOT** this full interactive model evaluation. The existing deterministic `run_dialogue` accepts up to 5 exact option-value answers on supplied TaskSpecs; it does not constitute Qwen-generated multi-turn dialogue nor natural-language answer parsing. Build an interactive model harness with versioned transcripts, answer source, seeds, hashes, depth and termination.

## 5. Prespecified Table III: only comparable systems

All prospective runs must use the SAME source records, same structured-output schema, evaluation gold, failure policy and compute cap. Ablations share the same pinned 8B checkpoint, decoding parameters and prompt budget; remove only the named component. Source-ablated Blind legitimately lacks scene/dialogue context, and must not receive it indirectly from caches, gold, or TaskSpec sidecars.

1. `Raw Qwen3-8B`: full source, direct task/clarification prediction, no Manager modules.
2. `Manager Qwen3-8B`: all seven stages, global constraints and question loop d<=5.
3. `Context-Blind Qwen3-8B`: raw utterance but no scene/dialogue/capability-derived evidence, same task schema and evaluation. This reproduces the input-ablation principle, not necessarily identical semantics to the historical 21/120 implementation.
4. `Manager minus structured task graph`: flat independent slot/operation representation; otherwise same pipeline.
5. `Manager minus joint grounding`: local independent candidate grounding; preserve all other components.
6. `Manager minus action-equivalence readiness`: route by a fixed scalar/model readiness judgment while retaining task-graph input.
7. `Manager minus targeted question selection`: fixed/random eligible question; same state and depth.
8. `Manager minus persistent clarification state`: re-parse entire dialogue each turn; same answers and depth, no gold.
9. `Manager Qwen3-4B` and `Manager Qwen3-1.7B`: same full architecture, same inputs, different pinned checkpoint sizes; run both with comparable hardware and settings.

**Do not** put the old 96/120 and 21/120 numbers into new task-graph/success@5 cells. Those historical figures are for old route protocols only, not comparable new-task scores.

Suggested main table columns: `Intent`, `First-turn E/C macro-F1`, `False-ready rate`, `Exact task@0`, `Dependency F1`, `Correct task@5`, `Mean turns`, `p50/p95 ms`. Keep `Slot F1`, `ambiguity set F1`, evidence and GPU metrics in secondary tables.

## 6. Reviewer case ledger

A preliminary historical gold-visible 120-case ledger is `CASE_REVIEW_120_LEGACY_MANAGER.md`; it diagnoses 37 disagreements of the *capability-repaired* 83/120 system. Each new experimental row must add:
- `case_id`, `stratum`, `annotation_status`, `gold_readiness`;
- `gold_task_graph_reference`, `generated_task_graph`, `manager_first_turn`, `baseline_outputs`;
- `task_graph_correct`, `missing/extra actions`, `wrong_grounding_bindings`, `missing_dependency`;
- `questions_by_depth`, `answer_source`, `wrong_question_targets`, `final_task_correct`, `turns_to_resolution`;
- `latency_tokens_gpu`, `manager_vs_raw_qwen`, `manager_vs_blind`, `stage_at_fault`, `adjudicator_notes`.
Report per-case **Manager wins, ties, regressions**; blind annotate new task correctness before showing comparator names. A lexical pattern matched to a gold-visible case is a *development clue*, not a causal correctness proof.

## 7. Statistical and release policy

- Lock benchmark splits, action equivalence normalizer, model checkpoint hashes, prompt schemas, confidence and failure policies **before held-out inference**.
- Use per-case paired comparisons (bootstrap confidence intervals, McNemar for binary correctness) and display stratified dependent-compound accuracy; avoid unadjusted significance shopping over many ablations.
- Keep every invalid parse, model timeout, false-ready and depth-cap in denominator; do not substitute gold if an LLM omits alternatives.
- Separate development/diagnostic Pilot-120, independent annotation-validation subset, and final untouched heldout. A post-hoc 114/120 regex diagnostic is not a publishable substitute for new Qwen predictions.
- Avoid distributing upstream-derived full source text outside the project's rights controls.

## Literature attribution

- v35 Goal-First: semantic action recovery baseline.
- CLARA (Park et al., 2024, DOI:10.1109/LRA.2023.3338514): contextual classification and clarification.
- AmbiK (Ivanova et al., ACL 2025, DOI:10.18653/v1/2025.acl-long.1593): paired ambiguous/resolved instructions.
- Global Grounding (Sucker & Henrich 2025, DOI:10.1109/LRA.2025.3560864): globally consistent referent assignments.
- CoDraw-iCR (Madureira & Schlangen, EACL 2023, DOI:10.18653/v1/2023.eacl-main.169), ClarifyVC (ICLR 2026): clarification quality and multi-turn grounding.
- KnowNo (Ren et al., CoRL 2023): preserve candidate uncertainty; no conformal guarantee is claimed for our heuristic.
- Bayesian Active Learning for Intent Disambiguation (2026): task-separating question selection; our initial question selector is a uniform heuristic.
