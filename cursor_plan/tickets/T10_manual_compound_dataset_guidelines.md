# T10 — Manual compound dataset guidelines and seed template

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Create the manual compound dataset annotation guidelines and seed template.

## Why this ticket exists

No current dataset cleanly gives gold compound ambiguity with project-specific multi-label ambiguity sets, strategy sequences, and safety-precondition cases. Manual data is required for the core contribution.

## Manual dataset target

Target final size: 150–250 validated examples.

Minimum categories:

| Category | Example pattern |
|---|---|
| referential + spatial | "Move that thing over there." |
| pragmatic + referential | "Can you deal with that thing?" |
| temporal + safety_precondition | "Heat it for a while." |
| pragmatic + safety_precondition | "Can you make this ready for the child?" |
| dialogue-resolved reference | "Put it next to the other one." with previous dialogue |
| scene-resolved reference | one possible target in scene |
| multiple safe interpretations | clarify |
| some unsafe interpretations | clarify with safety boundary or safety loop |
| all interpretations unsafe | face-preserving rejection |

## Required tasks

1. Create `docs/annotation/manual_compound_guidelines.md`.
2. Define every ambiguity label operationally.
3. Define route labels operationally.
4. Define `multi_step` and valid `strategy_sequence` patterns.
5. Define safety-precondition ambiguity separately from safety classification.
6. Create annotation CSV/JSONL template in `data/manual/manual_compound_template.csv` or `.jsonl`.
7. Create 10 seed examples only, marked `draft_seed_not_gold`.
8. Include fields for annotator ID and notes.

## Deliverables

- Annotation guidelines.
- Manual dataset template.
- 10 seed draft examples.
- Completion report.

## Acceptance criteria

- Guidelines are clear enough for two annotators to label independently.
- Seed examples are not marked as final gold.
- Safety project boundary is respected.
- `multi_step` has concrete sequence semantics.

## Validation approach

This ticket is primarily methodological or manual. Do not force artificial unit tests. Use schema checks, coverage matrices, independent review, sampled verification, and explicit evidence files. Any supporting deterministic script must still be developed with focused tests.

## Stop condition

Stop after guidelines and seed template. Do not compute kappa yet.

## Required manual dataset scope

Freeze a target of **50 adjudicated compound-ambiguity examples** unless the human records a revised target before annotation begins.

Create a coverage matrix that includes:

- all canonical ambiguity labels where feasible;
- at least two ambiguity labels per compound example;
- low, medium, and high risk;
- all five routes;
- capability statuses;
- simple and multi-stage strategy sequences;
- context-present and context-absent cases;
- difficult borderline and adversarial cases.

The ticket must produce annotation guidelines, seed templates, counterexamples, tie-breaking rules, and a pre-registration-style statement of how examples will be authored without inspecting model failures on the protected test set.
