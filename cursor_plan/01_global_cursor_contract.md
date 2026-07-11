# 01 — Global Cursor Execution Contract

Supply this document to Cursor for every unfinished ticket.

## Research boundary

Build and evaluate a **text-first Risk-Aware Ambiguity Manager for Compound Ambiguous Robot Commands**.

The system consumes:

```json
{
  "command": "string",
  "scene_context": "string | null",
  "dialogue_history": ["string"],
  "capability_context": "string | null"
}
```

The system operates only at the natural-language interpretation and routing layer. It does **not** implement perception, motion planning, navigation, grasping, actuation, or a complete safety classifier.

Raw-image/LVLM work is excluded from this execution plan. Scene information must be supplied as text, captions, object lists, or structured state.

## Frozen research outcome

The central question is whether explicit ambiguity-type, task-risk, capability, context, and uncertainty coordination improves routing decisions for compound ambiguous commands compared with direct LLM interpretation and fixed/degree-based policies.

The proposed manager must use a **supervised fine-tuned local open-source text LLM** with schema-constrained output. Deterministic policy code must consume the model's structured analysis and issue the consequential route.

## Canonical route labels

```text
execute
clarify
silently_resolve
face_preserving_rejection
multi_step
```

## Canonical ambiguity labels

```text
referential
spatial
pragmatic
temporal
quantitative
preference
commonsense
safety_precondition
capability
contextual
```

## Canonical schema authority

T01 is a completed historical ticket and contains conflicting legacy enum notes. **T10 defines schema version 2 and is authoritative for all unfinished work.** Do not rerun T01. Migrate completed T00–T09 outputs through the versioned T10 migration layer.

Canonical prediction enums after T10:

```text
risk_level: none | low | medium | high | unknown
capability_status: capable | conditional | incapable | unknown
```

Gold fields may be `null` only when that field is genuinely unavailable and the record is ineligible for the corresponding metric. Predictions must use an allowed value rather than `null`.

## Interpretation and information-structure requirement

Every LLM-backed system must emit validated structured output containing:

- speech act / intent;
- Core Propositional Content (CPC): action, actor, object, destination, spatial relation, quantity, time, recipient, tool, conditions, and constraints;
- candidate interpretation frames;
- a selected interpretation only when evidence uniquely supports it;
- unresolved slots;
- supporting evidence from command, scene, dialogue, or capability context;
- ambiguity labels;
- risk and capability status;
- context-sampling uncertainty;
- recommended route and optional strategy sequence;
- resolved slot values when `silently_resolve` is chosen;
- clarification targets/question or rejection reason where applicable.

## Correctness dimensions

Never collapse these into one score:

1. Intent/speech-act correctness.
2. CPC and slot correctness.
3. Candidate-set completeness and precision.
4. Evidence faithfulness and contradiction avoidance.
5. Ambiguity and unresolved-slot correctness.
6. Risk and capability correctness.
7. Silent-resolution value correctness.
8. Route correctness.
9. Clarification/rejection appropriateness.
10. Safety-sensitive behaviour.

A correct route with a wrong interpretation is still an interpretation failure. A correct interpretation with a wrong route is still a policy failure.

## Seven mandatory comparison systems

All seven are mandatory in the frozen experiment:

1. `always_execute`;
2. `always_clarify`;
3. `always_silently_resolve`;
4. `direct_base_llm`;
5. `degree_based_router`;
6. `context_blind_manager`;
7. `full_finetuned_type_risk_manager`.

Do not downgrade any of these to optional or stretch status.

## Gold and evaluator rules

- Official scores come from verified source-native labels or human-adjudicated gold.
- The evaluated model may assist scenario authoring but must not create official gold without independent human verification.
- A generative LLM must not be the primary judge of another model.
- Deterministic structured comparison is the official evaluator.
- A learned semantic verifier is secondary and may be used officially only after human meta-evaluation; otherwise it remains exploratory.
- Every metric must declare required fields, eligible records, included sources, excluded records, and denominator.
- Missing gold fields are excluded, never scored as incorrect.

## Local model and fine-tuning rules

- Assume local-only inference and training.
- All generative calls go through `ModelClient.generate_json(...)`.
- Inference runtime details stay behind adapters.
- Record exact base model, revision, licence, quantisation, context size, decoding settings, runtime, and hardware.
- The direct baseline and proposed manager must share the same base model and revision.
- The proposed manager must use the required supervised adapter produced in T28.
- Model, prompt, threshold, and checkpoint selection use train/dev only.
- If mandatory local fine-tuning cannot be completed truthfully, the project is `BLOCKED`; do not silently substitute a prompt-only proposed system.

## Protected-test rules

- Do not access protected test data before T29 passes.
- Test data may not be used for prompt design, debugging, thresholds, few-shot examples, model selection, fine-tuning, route-policy refinement, or evaluator calibration.
- T28 trains/selects using train/dev only.
- T30 performs protected execution.
- Any post-test change creates a new protocol version and requires rerunning every affected condition.

## Anti-hallucination rules

- Do not invent fields, licences, mappings, labels, examples, counts, model capabilities, metrics, or results.
- Preserve raw model output separately from parsed output.
- Do not silently skip records or failed model calls.
- Use `BLOCKED_TODO_VERIFY` when a required fact cannot be verified.
- Use `TODO_VERIFY_LABEL_MAPPING` for uncertain mappings and exclude those labels from official scoring.
- Use `NOT_COMPUTED` for an unproduced promised result.

## Provenance rules

Every record must preserve, where applicable:

- `source_dataset`, `source_id`, and `original_split`;
- `schema_version`, `mapping_version`, and `group_id`;
- source licence reference;
- label provenance/confidence and annotation status;
- generation model, prompt hash, seed, timestamp, and human-review status;
- metric eligibility fields.

Every builder reports input, output, skipped, invalid, duplicate, and per-reason counts.

## Governance rules

- Maintain a versioned generative-AI use log covering authoring, code, model inference/training, analysis, and writing support.
- Maintain model and dataset licence registers.
- Record the institutional/supervisor determination for human annotation and meta-evaluation before collecting human judgements.
- Do not expose annotators to model-proposed gold labels.

## Reproducibility rules

Every experiment records:

- run ID and timestamp;
- Git commit or source snapshot;
- schema, dataset, split, prompt, route-policy, eligibility, configuration, and protocol hashes;
- base model, adapter, revision, quantisation, decoding, and seeds;
- hardware/software environment;
- runtime, token counts where available, invalid outputs, repairs, and cost estimate;
- input, raw output, parsed prediction, and metric paths.

Never overwrite prior gold, splits, predictions, adapters, or reports.

## Test-driven development policy

Use Red–Green–Refactor for deterministic behaviour, including schema migration, validation, eligibility, splitting, routing, context sampling, metric code, protocol guards, and report generation. Do not force unit tests for subjective annotation or qualitative analysis; use blind review, evidence logs, and checklists.

## Ticket isolation

- Work on one ticket only.
- Inspect real repository artifacts instead of relying on chat memory.
- Stop after the ticket's stage gate.
- Do not rerun T00–T09. T10 may migrate their artifacts without recreating them.
- Do not continue without human approval.

## Required completion report

```markdown
# Ticket completion report

## Ticket
- ID:
- Title:

## Preconditions checked
- ...

## Files created/changed
- ...

## Tests written first, if applicable
- Test files:
- Initial failing behaviour:

## Commands run
- ...

## Validation results
- ...

## Acceptance criteria status
- [ ] ...

## Counts / metric outputs
- ...

## Evidence and traceability
- Input hashes/versions:
- Output paths:
- Config/prompt/model versions:

## Unresolved TODO_VERIFY / BLOCKED items
- ...

## Stage gate
PASS/FAIL/BLOCKED:
Reason:
```

Any failed mandatory acceptance criterion means `FAIL` or `BLOCKED`, never an optimistic pass.
