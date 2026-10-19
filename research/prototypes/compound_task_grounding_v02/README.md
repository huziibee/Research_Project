# Compound task grounding and clarification — v0.2 development research

This project adds an experimental task-graph representation and action-readiness
verifier to the archived Pilot-120 study. **It does not modify frozen labels,
old predictions or the v35 paper.** It is an exploratory diagnostic on the
already-studied Pilot-120 set, not a new confirmatory benchmark.

## What works here

- **Model boundary:** `compound_manager.model_adapter` constructs a gold-free
  source-only prompt; `pipeline.LanguageModel` injects any model backend.
  `FixtureModel` uses ChatGPT-authored interpretations of seven previously
  inspected Pilot-120 examples and one synthetic compound case.
- **Task graph:** `compound_manager.engine` enumerates entity/action-scope
  assignments, expands lookup dependencies and arithmetic, verifies complete
  ordered action-graph equivalence, and does not require a *single atomic action*.
- **Grounding:** exact evidence-quote validation, expression/lookup checks,
  cross-action shared-variable diagnostics, and conservative abstention on
  unsupported quotes and unavailable candidate domains.
- **Clarification:** choose a distinguishing variable, accept only an exact
  in-domain answer, update dialogue state and re-evaluate up to five rounds.
- **Research metrics:** a *separate* source-only regex baseline over Pilot-120.
  This is a readiness-classification diagnostic, not an LLM or action-graph
  success score. Its output can be compared with existing 83/120 and the gated
  always-ready reference without confusing it with the actual task compiler.

## Run

```sh
python -m unittest discover -s tests -v
python run_demo.py --all
python run_demo.py CA-0608 --answer quantity_ml=20
python run_demo.py SYN-DEPENDENT-001 --answer container=B1
python run_pilot120_diagnostic.py --repo-root /path/to/Research_Project --out /tmp/compound_v02
```

Python >=3.11, standard library only. Source-probe scoring needs the real repo
files. The prompt model endpoint is intentionally injectable: no API key,
local Qwen checkpoint or GPU is present in the authorship runtime. To run a
model, implement `LanguageModel.generate`, use the already pinned
`Qwen/Qwen3-8B` checkpoint, and supply the model's JSON to `parse_task_spec`.

## Pilot-120 exploratory results

The locked generic lexical source probe identifies 13/23 first-turn
clarifications and zero false clarifications on the 76 gold-execute items.
It scores **89/99** on execute-vs-clarify, and **106/120** when overlaid
on the independently archived repaired refusal gate. Original archived
capability repaired baseline is **83/120** and gated always-ready is **93/120**.
Remaining hybrid mistakes: 4 E->R, 8 C->E, 2 C->R. This is *not*
independent semantic parsing and is vulnerable to the panel's explicit
textual marker patterns. This panel informed development; no confirmatory
p-value or population generalization is claimed.

The graph engine has 35 local tests (including the inherited v0.1 tests).
These local fixtures were manually authored and previously gold-visible.
They demonstrate execution paths, not 7/7 blind accuracy. The source probe
produces only coarse unverified action scaffolds for the 120 records.

## Papers → architectural decisions

| Paper | Reused design principle | Module / test |
|---|---|---|
| **CLARA** (Park et al. 2024) | Distinguish clear from clarifiable commands; ask contextual questions | `pipeline.run_dialogue` |
| **AmbiK** (Ivanova et al. 2025) | Contrast unresolved and context-resolved variants; candidate sets | example fixtures + candidate tests |
| **Global Grounding** (Sucker & Henrich 2025) | Globally consistent joint bindings, not independently guessed slots | `engine._candidate_bindings`, `$lookup`, `dependency_analysis` |
| **CoDraw-iCR** (Madureira & Schlangen 2023) | Separately measure decision to ask and question itself | `engine._partition_score`, `pipeline.answer_turn` |
| **ClarifyVC** (Zhou et al. 2026) | Multi-turn clarification and state retention | `pipeline.run_dialogue`, five-round cap |
| **KnowNo** (Ren et al. 2023) | Preserve competing candidates when unsure | `engine.resolve` (NOT conformal-calibrated) |
| **Bayesian active learning for intent disambiguation** (2026) | Choose question by expected reduction over candidate tasks | uniform candidate-partition heuristic (NOT full Bayesian inference) |
| **v35 Goal-First** | Recover whole requested job before deciding readiness | `model_adapter.build_model_prompt`; original pinned Qwen remains comparator |

## Unresolved scientific and engineering limitations

- Raw-text -> full task graph is **not** automated end-to-end with actual Qwen
  in the current environment. The input adapter/contract is ready but no
  model-generated 120-row graph stream has been evaluated.
- Exact quote presence does not show that an inference is semantically correct.
  Candidate recall and scene coverage remain unverified; a unique *generated*
  candidate does not prove that the instruction is truly ready.
- No physical execution, capability/authorization/risk policy, perception,
  independent task-graph gold, or validated real-user clarification study.
- Do not make a new route label out of a risk category; keep ambiguity
  readiness separate from capability and safety.
- Source data redistribution rights remain governed by the parent repo's
  dataset rights register. Avoid exposing full upstream source packets in new
  stand-alone public releases.

A next confirmatory experiment requires independent graph/candidate/ambiguity
annotations on a held-out set with single, independent-compound and dependent-
compound commands, model-grounded end-to-end predictions, and matched-depth
clarification controls. Keep both old and new protocols versioned.