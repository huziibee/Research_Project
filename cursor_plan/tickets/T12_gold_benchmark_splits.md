# T12 — Gold benchmark splits and leakage checks

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Create train/dev/test/gold splits with leakage checks.

## Why this ticket exists

Final metrics require held-out evaluation. Weak training data and gold evaluation data must stay separate.

## Split principles

- Gold evaluation should be balanced and manually validated.
- Test/gold must not be used for prompt tuning or fine-tuning.
- Similar examples should not appear across splits.
- Source provenance must be preserved.

## Suggested split sizes

If enough records exist:

| Split | Purpose | Suggested proportion |
|---|---|---:|
| train | prompting/fine-tuning/rule development | 70% |
| dev | prompt/rule tuning | 15% |
| test | final evaluation | 15% |
| gold/manual | adjudicated manual benchmark | separate or test-only |

Manual compound target:

```text
150–250 total examples
train/dev/test only if enough; otherwise reserve all manually adjudicated examples for gold evaluation and use no manual examples for training.
```

## Required tasks

1. Load weak pool and adjudicated manual data if available.
2. Deduplicate exact commands.
3. Implement basic near-duplicate checks using normalized text similarity.
4. Split by source and route/ambiguity labels where possible.
5. Write split manifests:

```text
data/splits/train.jsonl
data/splits/dev.jsonl
data/splits/test.jsonl
data/splits/gold_manual.jsonl if available
```

6. Produce distribution reports by source, route, and ambiguity labels.
7. Produce leakage report.

## Deliverables

- Split files.
- Split manifest report.
- Leakage report.
- Completion report.

## Acceptance criteria

- No exact duplicate command appears across splits.
- Source/route distributions are reported.
- Gold/test files are protected from training use.
- If data is insufficient, report why and create only valid splits.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after splits and leakage report. Do not build model code.

## Stronger split and leakage requirements

Create fixed `train`, `dev`, `test`, and `challenge` manifests.

Leakage controls must include:

- exact normalized-text duplicates;
- near-duplicate similarity detection;
- same template/seed family;
- paraphrase siblings;
- dialogue episode/scene grouping;
- generated variants;
- shared `group_id` enforcement.

Use group-aware stratification where possible for route, risk, ambiguity type, compound status, and source. Save the seed, algorithm, manifest hashes, and a signed/frozen test declaration. Unit tests must fail if any group appears in more than one split.
