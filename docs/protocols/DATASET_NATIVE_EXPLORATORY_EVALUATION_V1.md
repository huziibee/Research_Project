# Dataset-native exploratory evaluation v1

## Purpose

This is the post-T41 development study. It asks what each available source can
actually answer, rather than forcing every source into a single ambiguity-type
benchmark. T39 and T41 remain frozen and are not inputs to model selection,
prompt tuning, or reruns.

## Core rule

Each metric is reported only on records that contain its native source target.
An absent target is `NOT_COMPUTED`, not a negative label and not a reason to
exclude the dataset from all other questions.

## VAGUE correction

VAGUE's canonical `scene_context` is the textual image caption from
`source_metadata.meta.caption`; the converted dataset contains no image bytes.
The planned ablation is therefore `command_only` versus
`command_plus_textual_caption`. It measures paired caption benefit only after
the pair construction, system binding, and analysis are frozen.

VAGUE has 1,677 records with a source solution triplet (`intent`), parsed
slots, a correct resolved interpretation, and four candidate interpretations.
This makes it the strongest source for intent/goal recovery. The current
general evaluator measures speech-act accuracy, not VAGUE tuple-goal accuracy;
a deterministic goal-intent scorer is required before that metric is run.

## Source-native questions

- AmbiK: ambiguity presence/type and clarification target.
- Indirect Requests: pragmatic ambiguity and available argument-slot recovery.
- VAGUE: intended goal recovery, candidate/selected interpretation, and
  textual-caption ablation.
- CLARA: source-native routing/capability and textual context ablation.
- CoDraw-iCR v2 and ClariQ: clarification-target quality only after a frozen
  semantic scorer; neither supports a robot-routing claim by default.

All current source labels are weak/mapped. Results are exploratory development
evidence, never adjudicated or generalisation evidence.

## Systems

Every future run must name immutable hashes for: base model revision, adapter
(if used), manager implementation, prompts, render/tokenizer, decoder, and
the input manifest. The repaired `interpretation_manager_v2` is presently
synthetic-fixture-tested only, so it must receive its own binding before it is
treated as an inference system. Legacy manager baselines must remain distinct
from that repair.

## Immediate executable preparation

Run the eligibility audit against the protocol. It verifies field coverage and
creates no predictions or scores:

```powershell
python scripts/audit_dataset_native_evaluation.py `
  --protocol configs/evaluation/dataset_native_exploratory_evaluation_v1.json `
  --root . `
  --output outputs/dataset_native_eligibility_audit_20260902.json
```

The deterministic scorer is `scripts/score_vague_goal_intent.py`. It compares
a frozen `goal_triplet` prediction (`subject`, `action`, `object`) with VAGUE's
source solution triplet, preserves paired conditions, and refuses incomplete
coverage. It must not substitute CPC or route correctness for intent. A real
run remains blocked until its system/output binding is frozen.
