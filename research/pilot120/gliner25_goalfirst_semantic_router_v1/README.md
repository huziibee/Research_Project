# GLiNER2.5-Decide: frozen Goal-First semantic router v1

**Exploratory negative/diagnostic result.** Best direct accuracy is **77/120 (64.17%)**, using intent + speech act + 13 task slots (C). Macro F1 is **0.3170**. It predicts EXECUTE for **19/21 required refusals** and **23/23 clarification cases**. This is not a reliable replacement for the existing router.

The primary full-semantic condition F scores **43/120**, macro F1 **0.3491**. It has zero refusal-to-execute errors, but correctly refuses only 12/21 (the other nine clarify), recognizes 10/23 clarifications, and executes only 21/76 executable tasks. Best-by-accuracy C is not best-by-macro-F1; the selection rule was locked before inference.

Protocol, renderer, revision, frozen artifact hashes, field coverage, exclusions, and reproduction commands: [experiment guide](../../../docs/experiments/GLINER25_GOALFIRST_SEMANTIC_ROUTER_V1.md). The paper and all frozen evidence are unchanged.

## All conditions

E/C/R abbreviate EXECUTE/CLARIFY/REFUSE. Rows in each confusion matrix are gold, columns are predicted. All conditions have 120 unique records and zero failures; all 840 inference rows are retained.

| Condition | Correct /120 | Accuracy | Macro F1 | E?E | E?C | E?R | C?E | C?C | C?R | **R?E** | R?C | R?R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A_intent_only | 70 | 58.33% | 0.2456 | 70 | 6 | 0 | 23 | 0 | 0 | 21 | 0 | 0 |
| B_intent_grounding | 63 | 52.50% | 0.3126 | 56 | 20 | 0 | 16 | 7 | 0 | 11 | 10 | 0 |
| C_intent_task_slots | 77 | 64.17% | 0.3170 | 75 | 1 | 0 | 23 | 0 | 0 | 19 | 0 | 2 |
| D_grounding_capability | 57 | 47.50% | 0.3433 | 37 | 0 | 39 | 5 | 0 | 18 | 1 | 0 | 20 |
| E_full_without_risk | 25 | 20.83% | 0.2090 | 3 | 43 | 30 | 0 | 10 | 13 | 0 | 9 | 12 |
| F_full | 43 | 35.83% | 0.3491 | 21 | 25 | 30 | 0 | 10 | 13 | 0 | 9 | 12 |
| G_action_readiness_full | 29 | 24.17% | 0.2333 | 4 | 37 | 35 | 0 | 7 | 16 | 0 | 3 | 18 |

An all-EXECUTE reference scores 76/120, macro F1 0.2585, with all 23 clarifications and all 21 refusals incorrectly executed. Best C is only one case above this majority-route reference. Intent only (A) scores 70/120: the concise interpretation alone does not recover routing.

## Per-class metrics for every condition

| Condition | Gold class | Precision | Recall | F1 | Support |
| --- | --- | ---: | ---: | ---: | ---: |
| A_intent_only | EXECUTE | 0.614035 | 0.921053 | 0.736842 | 76 |
| A_intent_only | CLARIFY | 0.000000 | 0.000000 | 0.000000 | 23 |
| A_intent_only | REFUSE | 0.000000 | 0.000000 | 0.000000 | 21 |
| B_intent_grounding | EXECUTE | 0.674699 | 0.736842 | 0.704403 | 76 |
| B_intent_grounding | CLARIFY | 0.189189 | 0.304348 | 0.233333 | 23 |
| B_intent_grounding | REFUSE | 0.000000 | 0.000000 | 0.000000 | 21 |
| C_intent_task_slots | EXECUTE | 0.641026 | 0.986842 | 0.777202 | 76 |
| C_intent_task_slots | CLARIFY | 0.000000 | 0.000000 | 0.000000 | 23 |
| C_intent_task_slots | REFUSE | 1.000000 | 0.095238 | 0.173913 | 21 |
| D_grounding_capability | EXECUTE | 0.860465 | 0.486842 | 0.621849 | 76 |
| D_grounding_capability | CLARIFY | 0.000000 | 0.000000 | 0.000000 | 23 |
| D_grounding_capability | REFUSE | 0.259740 | 0.952381 | 0.408163 | 21 |
| E_full_without_risk | EXECUTE | 1.000000 | 0.039474 | 0.075949 | 76 |
| E_full_without_risk | CLARIFY | 0.161290 | 0.434783 | 0.235294 | 23 |
| E_full_without_risk | REFUSE | 0.218182 | 0.571429 | 0.315789 | 21 |
| F_full | EXECUTE | 1.000000 | 0.276316 | 0.432990 | 76 |
| F_full | CLARIFY | 0.227273 | 0.434783 | 0.298507 | 23 |
| F_full | REFUSE | 0.218182 | 0.571429 | 0.315789 | 21 |
| G_action_readiness_full | EXECUTE | 1.000000 | 0.052632 | 0.100000 | 76 |
| G_action_readiness_full | CLARIFY | 0.148936 | 0.304348 | 0.200000 | 23 |
| G_action_readiness_full | REFUSE | 0.260870 | 0.857143 | 0.400000 | 21 |

## Frozen baselines

| System | Correct /120 |
| --- | ---: |
| Goal-First original | 56 |
| GLiNER best semantic condition C | 77 |
| GLiNER primary full condition F | 43 |
| Post-capability repaired Goal-First | 83 |
| Capability oracle | 87 |
| Raw Qwen | 96 |
| Fine-Tune | 92 |

The original router is compared against the exact same saved Goal-First interpretations used by GLiNER. The 83/87 baselines use saved per-case correctness maps. See the guide for exact archive members and hashes.

## Paired case analysis

| Comparator (first) vs best GLiNER C (second) | Both correct | Comparator only | GLiNER only | Both wrong | Exact McNemar p |
| --- | ---: | ---: | ---: | ---: | ---: |
| Goal-First original | 35 | 21 | 42 | 22 | 0.0111414 |
| Post-capability router | 48 | 35 | 29 | 8 | 0.532309 |

Two-sided exact McNemar tests condition on discordant cases. These p values are unadjusted, the best condition was selected on Pilot-120, and this set already informed development. They do not establish a confirmatory improvement or safety.

## Requested cohorts (best C)

| Cohort | Correct/fixed | Still wrong | Predicted E | Predicted C | Predicted R |
| --- | ---: | ---: | ---: | ---: | ---: |
| Final intent-positive / original route-wrong (63) | 42 | 21 | 62 | 1 | 0 |
| Gold CLARIFY (23) | 0 | 23 | 23 | 0 | 0 |
| Gold REFUSE (21) | 2 | 19 | 19 | 0 | 2 |
| Original false refusals (57: 39 E + 18 C) | 38 | 19 | 56 | 1 | 0 |

The 63-case cohort uses the final matched two-judge intent-positive flags, not an independent human gold interpretation. The older sprint list substitutes CA-0878 for CA-0845; the final cohort is used here. Exact cohort IDs are in `metrics.json`. The three final intent-negative IDs are CA-0149, CA-0460, CA-0878.

Original Goal-First recognized 3/23 clarifications; the previous raw-source GLiNER probe recognized 1/23. Best C recognizes 0/23, whereas primary F recognizes 10/23. The previous raw-source probe used different inputs and label descriptions, so this is descriptive context, not a matched causal input comparison.

## Risk field and action readiness

- Adding risk (E ? F) improves 25/120 to 43/120: **19 wrong?correct, 1 correct?wrong**, net +18. Removing the risk field hurts this frozen comparison.
- Action readiness G scores **29/120**, versus direct full F **43/120** and best direct C **77/120**. Against F, G loses 21 correct cases and gains seven, net ?14. It is worse in this experiment.
- G has zero R?E but only 4/76 correct EXECUTE routes, 7/23 correct clarifications and 18/21 correct refusals. Avoiding false execution through widespread non-execution is not successful routing.

## Answers to the research questions

1. **Dependable semantic-to-action conversion? No.** C improves aggregate accuracy over original Goal-First, but misses all clarifications and executes 19 required refusals; F is worse than the original overall.
2. **Beats original 56/120?** Best C does (77/120); primary F does not (43/120).
3. **Beats capability-repaired 83/120? No.** Neither best C nor primary F does.
4. **Preserves 21 required refusals safely?** Best C does not: 19 false executes. F blocks execution for all 21 but only 12 are correctly refused; nine incorrectly clarify.
5. **Improves 23 clarifications?** Best C does not (0/23, versus original 3/23). F does (10/23), with substantial losses on executable tasks.
6. **Does removing risk help? No.** F with risk beats E without risk by 18 correct cases.
7. **Is action readiness better? No.** 29/120 versus direct F 43/120 and best C 77/120.
8. **Worth adding to the paper?** Worth considering as an exploratory negative/diagnostic result or appendix, demonstrating that high automatic intent screening does not solve downstream routing. It does not support a successful GLiNER router or safe end-to-end robot action claim. The paper has not been edited.

## Evidence and replay

- `protocol.json`: prespecified renderer fields, labels, model revision, input hashes, exclusions and best-selection rule.
- `input_audit.json`, `renderer_length_audit.json`, `tokenization_audit.json`: 120-record structure, field coverage, input sizes, no-truncation evidence and nominal-length limitation.
- `runtime.json`: observed Python/package/platform/device data and all ten model-file hashes.
- Seven `*.predictions.jsonl` files: text-free predictions, confidence, failure flag, input/protocol hash, elapsed time.
- `metrics.json`: exact unrounded metrics, confusion matrices, paired tests, cohorts and selection.
- `paired_case_ledger.jsonl`: gold/baseline flags and seven routes per ID; no semantic/source text.
- `failed_rows.json`: empty, zero failures.
- `review.json`: independent verification.
- `SHA256_FINAL.json`: observed output hashes.

Standard-library saved-result replay from repository root:

```powershell
py -3.11 scripts/experiments/gliner25_goalfirst_semantic_router_v1.py score
```

See the guide for model installation and isolated inference replay. Case source text and upstream redistribution rights remain governed by the controlled evidence archive; this new result folder contains no rendered interpretations or source packets.
