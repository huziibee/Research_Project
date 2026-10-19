# Compound ambiguity source-grounding repair — v0.3 (19 October 2026)

**Status:** implemented and development-verified; Qwen TaskSpec inference has **not** been executed. Existing frozen source/gold, v35 paper and earlier model outputs remain unchanged.

## What changed

- New `compound_manager/source_probe_v03.py` adds four **general source-evidence relationships** on top of v0.2: (i) two pending objects matching an underspecified singular `selected` command, (ii) a nonunique recipient role with explicitly required recipient identity, (iii) two viable storage units without a selected unit identifier, (iv) two range-specific measuring instruments with an unknown expected range. The rules use **no record ID, gold label, route or capability field**.
- New `compound_manager/contextual_v03.py` carries these source-only alerts into Qwen's TaskSpec prompt. If the Qwen-generated graph claims readiness while a source-backed multiplicity alert remains, it returns `needs_context_repair` rather than incorrectly asserting a unique grounded task. **This is an abstention, not evidence that the graph was repaired or that a successful clarification occurred.**
- New `run_qwen120_v03.py` runs the prospective source-only TaskSpec pipeline with the exact original pinned Qwen3-8B model, resumable JSONL output, source hash check, no gold in prompts and explicit failures in the denominator. Old `run_qwen120.py` is retained for direct comparison.
- New regression tests verify positive and negative forms of all four source patterns, prompt leakage exclusion, task-graph preservation, and the full 120-case development panel on GitHub CI. Pattern-specific tests only validate engineering behaviour; they are not held-out examples.

## Observed results: contextual readiness rule diagnostic ONLY

These results are from GitHub Actions [run 39212061999](https://github.com/huziibee/Research_Project/actions/runs/39212061999) on the 120 existing Pilot-120 source records. They are not Qwen predictions or verified complete task graphs.

| Condition | Route agreement |
|---|---:|
| Earlier capability-repaired v35 Goal-First | 83/120 |
| v0.2 lexical source probe + archived refusal gate | 106/120 |
| **v0.3 contextual source probe + same archived refusal gate** | **114/120** |
| **v0.3 source-only readiness, restricted to original E/C records** | **99/99** |

New hybrid confusion matrix (gold rows / prediction columns Execute, Clarify, Refuse):

```
Gold Execute: [72, 0, 4]
Gold Clarify: [ 0,21, 2]
Gold Refuse:  [ 0, 0,21]
```

The ten originally missed clarify cases (source-only v0.2) are now identified: CA-0056 and CA-0092 (selected item), CA-0078 (recipient role), CA-0070/CA-0552/CA-0714/CA-0727/CA-0786 (destination unit), CA-0671/CA-0845 (instrument range). Their source evidence is retained in the per-case diagnostic. Only **eight** improve hybrid accuracy, because the historical refusal gate overrides CA-0552 and CA-0727.

The six remaining hybrid errors are CA-0042, CA-0203, CA-0259, CA-0369 (gold EXECUTE) and CA-0552, CA-0727 (gold CLARIFY). All six belong to the *unchanged archival refusal gate*. **The ambiguity-only research task should evaluate the 99 E/C cases separately.** Do not call 114/120 complete-task correctness.

This result is specifically **exploratory and post-hoc**. The four rule families were developed after seeing the ten errors and are effective on a dataset with highly explicit, templated context descriptions. 99/99 on this previously inspected panel does not establish generalization. Evaluate Qwen predictions and independently adjudicated task graphs on a new untouched test set before publication claims.

## User run commands (from Research_Project root)

Python 3.11 is used for compatibility with the historical project. The **preflight requires no GPU**:

```sh
cd research/prototypes/compound_task_grounding_v02
python -m unittest discover -s tests -v
python run_pilot120_diagnostic_v03.py --repo-root ../../.. --out results/pilot120_source_probe_v03_dev_run
python run_qwen120_v03.py --source ../../../data/annotations/pilot_120_v1/source_canonical.jsonl --output ../../../outputs/compound_qwen_v03 --preflight
```

Then, on an environment with the **pinned** `Qwen/Qwen3-8B` checkpoint and working PyTorch/Transformers/bitsandbytes CUDA stack:

```sh
python run_qwen120_v03.py --source ../../../data/annotations/pilot_120_v1/source_canonical.jsonl --output ../../../outputs/compound_qwen_v03 --ids CA-0056
python run_qwen120_v03.py --source ../../../data/annotations/pilot_120_v1/source_canonical.jsonl --output ../../../outputs/compound_qwen_v03
```

Only `--preflight` is tested without Qwen weights. Inference should be done in a clean model environment; GPU errors and invalid generations remain explicit failures in the JSONL. Do not overwrite historical artifacts.

## Research-paper mapping

- **AmbiK** (Ivanova et al., 2025): distinguish ambiguity already resolved by context from an action-changing alternative; motivates paired positive/negative tests.
- **CLARA** (Park et al., 2024): separate the need to ask from command understanding; motivates unresolved-variable targets instead of generic uncertainty.
- **Global Grounding** (Sucker and Henrich, 2025): globally consistent object bindings, recipient/destination references and dependent instrument choice. The source detector provides cues for the existing task-graph engine; it is not a reproduction of the paper's grounding algorithm.
- **CoDraw-iCR** (Madureira & Schlangen, 2023) and **ClarifyVC** (Zhou et al., 2026): question-target representation, stateful clarification and bounded multi-turn evaluation; the v0.2 engine already implements limited versions.
- **KnowNo** (Ren et al., 2023): preserve uncertainty rather than assert one ready action; v0.3's source-vs-graph abstention is a diagnostic heuristic, **not** conformal calibration.
- **Bayesian Active Learning for Intent Disambiguation** (2026): select questions that distinguish candidate complete tasks; the existing engine uses uniform candidate partitions, not Bayesian optimization.
- **v35 Goal-First Qwen3**: preserved as source-only semantic parser, not replaced with the lexical diagnostic; the updated model needs an actual fresh Qwen run.

## Important scientific limitations

This is a **post-hoc development rule repair** on Pilot-120, not an end-to-end learned compound ambiguity resolver. The model still must generate complete action graphs, cover alternatives it was not shown, preserve cross-action relationships, and generate good questions. Lexical evidence quotes do not prove complete scene grounding. The v0.3 gate may abstain on new genuinely ready tasks (false-positive multiplicity), which must be measured on independent unseen examples. Do not merge the draft research branch as a final scientific outcome until the prospective Qwen run and independent annotations are reviewed.