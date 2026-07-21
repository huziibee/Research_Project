# Cursor Execution Plan — Risk-Aware Ambiguity Manager

This archive is the corrected stage-gated plan for completing the research implementation and experiment.

## Current status

- **T00–T10 are completed and preserved.**
- **T11 is COMPLETE / PASS** with ethics determination `not_required` for supervisor-only annotation (`ETHGOV-001`).
- **T12 is ACTIVE** on branch `feature/t12-cluster-redesign` (cluster-native Stages A–I).
- Response-mode correction is committed; D-Final live smoke has **not** yet passed.
- `model_licence_register.selected_model` remains `null`.
- **T13/T14 are not active.** Ethics/governance no longer blocks supervisor-only annotation in principle, but technical and protocol gates remain unmet and no collection has begun.

## Key final decisions

- Text-only local LLM study; no LVLM/raw-image condition.
- Proposed manager uses mandatory local supervised fine-tuning.
- Context-sampling output variance is an implemented uncertainty feature.
- Interpretation/CPC correctness and route correctness are scored separately.
- Silent resolution must output and score actual resolved values.
- All seven comparison systems are mandatory.
- Official scores use human/source gold and deterministic code, not an LLM judge.
- Dataset/metric restrictions are machine-enforced.
- No calendar schedule constrains execution; stage gates do.
- Annotation annotators are the two project supervisors only; external annotators require reassessment.

## Seven mandatory systems

1. always execute;
2. always clarify;
3. always silently resolve;
4. direct base LLM;
5. degree-based router;
6. context-blind manager;
7. full fine-tuned type/risk-aware manager.

## Exact order

```text
COMPLETED: T00 T01 T02 T03 T04 T05 T06 T07 T08 T09 T10 T11

ACTIVE:
T12

NEXT AFTER T12 CLOSE-OUT:
T13 T14 T15
T16 T17 T18 T19 T20 T21 T22 T23
T24 T25 T26
T27 T28
T29
T30
T31 T32 T33
T34 T35
T36 T37 T38
```

## Core versus stretch

Mandatory core: T10–T24, T26–T33, T36–T38.

Stretch/nonblocking: T25, T34, T35. Their status must still be reported.

## Required reference documents

- `01_global_cursor_contract.md`
- `02_context_refresh_protocol.md`
- `03_dataset_roles_metrics.md`
- `04_hardware_model_strategy.md`
- `05_master_execution_plan.md`
- `06_copy_paste_prompt_template.md`
- `08_manual_gold_dataset_program.md`
- `10_interpretation_evaluation_framework.md`
- `11_proposal_alignment_contract.md`
- `12_core_stretch_policy.md`

## Completion definition

The project is complete only when T38 issues a core global `PASS`. A working build is insufficient: trusted gold, mandatory fine-tuning, all seven systems, protected predictions, interpretation/CPC metrics, routing metrics, eligibility denominators, statistics, ablations, traceability, governance, and audit evidence must exist.
