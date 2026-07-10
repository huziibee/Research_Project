# 01 — Global Cursor Execution Contract

This document must be supplied to Cursor for every implementation ticket.

## Project context

Build a **Risk-Aware Ambiguity Manager** for ambiguous robot/user commands.

Input shape:

```json
{
  "command": "string",
  "scene_context": "string | null",
  "dialogue_history": ["string"],
  "capability_context": "string | null"
}
```

Main output must be either:

1. a non-ambiguous interpretation ready for downstream safety/planning/execution layers, or
2. one of these canonical routing decisions:

```text
execute
clarify
silently_resolve
face_preserving_rejection
multi_step
```

Canonical ambiguity labels:

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

The project does **not** implement robot planning, robot execution, navigation, grasping, or a complete embodied safety system. It evaluates the natural-language coordination layer.

## Non-negotiable experimental rules

- The final test/gold set is protected and may be evaluated only after prompts, thresholds, rules, model selection, and hyperparameters are frozen.
- No test example may be used for prompt design, debugging, threshold selection, few-shot demonstrations, fine-tuning, or manual policy refinement.
- Every reported number must be traceable to a saved prediction file, gold file, configuration, and evaluation command.
- Dataset, schema, prompt, split, and model versions must be recorded.
- Negative and null results must be preserved and reported honestly.
- Do not change taxonomies or route semantics after the gold benchmark is frozen without creating a new version and rerunning all affected stages.

## Anti-hallucination rules

- Do not invent dataset fields, source licences, label mappings, examples, metrics, or citations.
- Do not silently skip rows.
- Do not fabricate files that were not produced by code.
- If a required file, label, licence, or source is missing, write `BLOCKED_TODO_VERIFY` and stop.
- If a dataset mapping is uncertain, mark it `TODO_VERIFY_LABEL_MAPPING` and exclude it from final metrics.
- If a planned result cannot be computed, report `NOT_COMPUTED` with the blocker.

## Scope rules

- Work on one ticket only.
- Do not continue to the next ticket unless the human explicitly approves.
- Do not edit unrelated files.
- Do not refactor broadly unless the ticket requires it.
- Prefer small, reviewable changes.
- Inspect existing artifacts on disk rather than relying on prior chat context.

## Test-driven development policy

Use TDD where behavior can be specified deterministically.

### TDD-required work

TDD is mandatory for:

- schema validation;
- dataset conversion and row accounting;
- duplicate/leakage detection;
- deterministic routing rules and threshold policies;
- metric calculations;
- statistical-test wrappers;
- experiment configuration validation;
- output parsing and JSON-schema enforcement;
- data split invariants;
- report-table generation from saved outputs.

For each TDD-required deliverable:

1. **Red:** write a failing test that expresses the acceptance behavior or regression.
2. **Green:** implement the smallest correct change that passes it.
3. **Refactor:** improve structure without changing behavior.
4. Save the exact test command and result in the completion report.

### TDD-not-appropriate work

Do not force TDD for subjective annotation decisions, literature justification, manual data writing, qualitative error interpretation, or exploratory model behavior. For these, use checklists, schema validation, review samples, and evidence logs.

### Test quality rules

- Tests must include normal, boundary, malformed, missing-field, and adversarial cases where applicable.
- Do not write tests that merely mirror the implementation.
- Do not weaken or delete tests to make a ticket pass without human approval.
- Tests must use tiny fixtures, never the full protected test set.
- Any bug discovered later must first receive a regression test.

## Data rules

Every converter must report:

- input row count;
- output row count;
- skipped row count;
- skip reasons and counts;
- duplicate count;
- invalid-record count;
- output path;
- source version/hash where available.

Preserve provenance fields:

- `source_dataset`;
- `source_id`;
- `original_split`;
- `label_confidence`;
- `mapping_version`;
- `source_license` or a verified licence reference;
- `group_id` where related examples must remain in one split.

Never overwrite gold datasets, split files, predictions, model outputs, or reports without a timestamped/versioned output directory.

## Reproducibility rules

Every executable experiment must record:

- run ID and timestamp;
- Git commit hash or explicit source snapshot ID;
- dataset and split manifest hashes;
- prompt and configuration hashes;
- model name, revision, quantisation, and adapter revision;
- decoding parameters and random seeds;
- hardware and software environment;
- runtime, token usage, invalid-output count, and compute/API cost where measurable;
- input and output file paths.

## Token-saving rules

- First inspect the file tree and relevant files.
- Summarize what exists before editing.
- Only open files needed for the ticket.
- Do not dump entire datasets into context.
- Use scripts to inspect columns, heads, counts, and distributions.
- Prefer targeted diffs over broad rewrites.
- Put long logs under `outputs/logs/` and summarize them.

## Required completion report

Every ticket must end with:

```markdown
# Ticket completion report

## Ticket
- ID:
- Title:

## Preconditions checked
- ...

## Files created/changed
- ...

## Tests written first, if TDD applies
- Test files:
- Initial failing behavior:

## Commands run
- ...

## Validation results
- ...

## Acceptance criteria status
- [ ] ...

## Row counts / metric outputs, if applicable
- ...

## Evidence and traceability
- Input hashes/versions:
- Output paths:
- Config/prompt versions:

## Unresolved TODO_VERIFY / BLOCKED items
- ...

## Stage gate
PASS/FAIL:
Reason:
```

If any acceptance criterion fails, the stage gate is `FAIL`.
