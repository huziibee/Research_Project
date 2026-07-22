# T15 — Gold splits, leakage controls, and experiment eligibility

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `03_dataset_roles_metrics.md`
- `08_manual_gold_dataset_program.md`

## Goal

Create leakage-safe train/dev/protected-test data and machine-enforced metric eligibility.

## Preconditions

- T10 migrated sources exist.
- T14 adjudicated gold exists.

## Required tasks

1. Inventory actual current sources, licences, gold fields, group IDs, and annotation provenance.
2. Define group-aware split policy covering siblings, paraphrases, templates, dialogue/scene families, context pairs, and source pairs.
3. Create train/dev/protected-test splits without exposing protected content to later development code.
4. Run exact, normalised, fuzzy, and semantic near-duplicate checks across splits and resolve every leakage finding.
5. Generate a versioned machine-readable experiment/dataset/metric eligibility manifest from verified fields.
6. Add record-level eligibility reason codes and excluded-count reports.
7. Create protected-data access controls/logging and hashes.
8. Create optional challenge-set partitions separately from the confirmatory test set.
9. Validate row accounting and source/group balance without forcing unsupported balance claims.

## Deliverables

- Frozen split manifests and hashes.
- Leakage reports.
- Eligibility manifest/schema/tests.
- Protected access guard/log.
- Count/source/group reports.
- T15 completion report.

## Acceptance criteria

- [ ] No related family crosses splits.
- [ ] Every metric has required fields and denominator logic.
- [ ] Protected records are inaccessible to ordinary development commands.
- [ ] Missing gold is excluded rather than scored wrong.
- [ ] Every input record is accounted for.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after splits and eligibility pass. Do not inspect protected examples or build model prompts from them.

## Update: source-development splits may proceed ahead of T14 (2026-07-22)

The **source-dataset development split programme** (weak-labelled AmbiK,
IndirectRequests, CoDraw-iCR v2, VAGUE, CLARA as primary; ClariQ as auxiliary) is a
separate, earlier-starting track from the **manual protected splits**:

- `source_train` / `source_dev` / `source_holdout` (plus `auxiliary_train` /
  `auxiliary_dev` for ClariQ) may be built and used for development purposes
  **without waiting for T14B/T14C adjudicated gold**. They are produced entirely from
  existing schema-v2 weak/derived labels and never invent gold.
- `source_holdout` is a **development-era holdout only**. It is explicitly **not** the
  final protected manual benchmark and must never be described, cited, or substituted
  as the `manual_protected_challenge_set`.
- The **manual protected splits** — i.e. the frozen partition(s) that will eventually
  contain the `manual_protected_challenge_set` (~300 adjudicated records, see
  `cursor_plan/08_manual_gold_dataset_program.md`) — remain gated on T14C adjudication
  as originally specified in this ticket's preconditions. Nothing in the
  source-development programme unlocks, previews, or substitutes for that gate.

See `configs/data/source_split_policy_v1.json`,
`src/ambiguity_manager/data/source_splits.py`,
`scripts/build_source_data_splits.py`, `tests/test_t15_source_splits.py`, and
`docs/reports/source_data_split_programme.md` for the implementation, tests, and
evidence of this earlier-starting source-development track.
