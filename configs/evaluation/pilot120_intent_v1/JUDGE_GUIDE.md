# Prediction-blind Semantic Goal Correctness judging guide

## What this evaluates

**Does the model's observable interpretation text state the same underlying user goal as the two pre-T39 gold intent references, irrespective of the terminal route it later chooses?**

This is intentionally separate from:
- CPC / slot correctness;
- ambiguity-label correctness;
- capability correctness;
- terminal-route correctness.

The frozen T39 prompt did **not** request a structured semantic intent summary, so this is a retrospective evaluation of **observable stated interpretation evidence**, not a claim about hidden/internal reasoning.

## Critical anti-copy rule

The source command is shown for context, but an exact/verbatim repetition of the source command is **not sufficient evidence of semantic interpretation**. The prepared candidate trace replaces exact source-command copies with `[VERBATIM_SOURCE_COMMAND_OMITTED]`.

Award semantic-goal credit only when the candidate **asserts, paraphrases, decomposes, or uses** the requested goal in its own interpretation. A bare quote/copy of the input is non-credit-bearing.

## Do not score CPC

Do **not** penalize a candidate merely for getting object identity, destination, quantity, time, recipient, tool, or another slot wrong. Those belong to CPC/resolution evaluation.

Only consider such content if it changes the **requested operation/end-state itself**. Examples:
- `inspect` vs `move` = intent-level difference;
- omitting a required second top-level action from `weigh then return` = intent-level difference;
- wrong destination while still understanding `move the object` = CPC error, not semantic-goal error.

## Five binary checks

### 1. `primary_goal_match`
TRUE iff the candidate asserts the same main requested operation/end-state as the gold references.

Paraphrases are fully acceptable. Exact wording is not required.

### 2. `required_action_set_match`
TRUE iff every materially requested **top-level action** is represented.

Example: `weigh then return` is not fully captured by `weigh` alone.

Do not turn ordinary slot details into actions.

### 3. `polarity_match`
TRUE iff action direction is preserved: perform / avoid / prohibit / do-not-perform.

`move X` and `do not move X` fail this check even though their words are nearly identical.

### 4. `explicit_enough`
TRUE iff the candidate states enough action semantics to identify the requested goal.

`The user issued a directive` or `perform the task` is insufficient by itself.

### 5. `no_incompatible_goal`
TRUE iff the candidate does not substitute or assert a materially incompatible user goal.

Extra discussion of ambiguity/risk does not count against it unless that discussion changes what the candidate claims the user wants.

## Derived outcomes

Do not manually alter these:

`semantic_goal_correct = all five checks TRUE`

`semantic_goal_component_score = number of TRUE checks / 5`

`goal_path_category`:
- `CORRECT`: all five checks pass;
- `PARTIAL`: primary goal + polarity + no incompatible goal pass, but action coverage and/or explicitness is incomplete;
- `WRONG`: otherwise.

The component score is a transparent diagnostic, **not a claim that the five components form a psychometrically calibrated interval scale**.

## Multiple gold references

Two independent pre-T39 `intent_text` annotations are supplied. Treat them as multiple semantic references, not strings to match. If phrasing differs, judge the common goal supported by the source.

If the references materially disagree on the user goal (not merely CPC details or phrasing), flag this in the rationale and do not guess; such a case should be routed to adjudication.

## Blinding

Do not inspect:
- system identity;
- terminal route;
- system correctness;
- aggregate T39 results;
- CPC score.

Judge each candidate independently. Do not pairwise-rank full-context and context-blind candidates.

## Output

Return one JSON object per `evaluation_id` matching `judge_output_schema.json` and set:

`"prediction_blind_attestation": true`

## Two-pass anti-comparison design

The 240 evaluations are split into `blind_judge_pass_1_120.jsonl` and `blind_judge_pass_2_120.jsonl`. Each pass contains exactly one condition for each underlying Pilot record. Run pass 2 in a **fresh evaluator context/session** after pass 1; do not provide pass-1 decisions to the pass-2 evaluator. This avoids presenting two versions of the same record side-by-side and reduces pairwise comparison/position effects.
