# Source-Dataset Development Split Programme (T15, source-development phase)

## Status

| Field | Value |
| --- | --- |
| Programme ID | `source_data_split_programme_v1` |
| Version | `1.0.0` |
| Seed | `20260722` |
| `manifest_hash` | `0671c2686b5c6cc1d3384f0cbe4541a8097e5feb293b55a04f990f00a0b7ef23` |
| `development_only` | `true` |
| `protected` | `false` |
| `valid_for_official_final_claims` | `false` |
| `source_holdout_is_not_manual_protected_challenge_set` | `true` |

## Purpose and scope

This programme creates a leakage-checked, group-aware **source-dataset** development
split of the schema-v2 weak-labelled pool, entirely independent of manual adjudication
(T14B/T14C). It does **not** wait for T14 and it does **not** produce or touch the
future `manual_protected_challenge_set` (see
`cursor_plan/tickets/T15_gold_splits_leakage_and_eligibility.md` and
`cursor_plan/08_manual_gold_dataset_program.md`). `source_holdout` is a
development-era holdout for early model-selection/threshold work only.

## Inputs

| Source | Path | Role | Records |
| --- | --- | --- | ---: |
| Primary weak pool | `data/processed/schema_v2/weak_pool/weak_pool_canonical.jsonl` | core / conditional-core (AmbiK, IndirectRequests, CoDraw-iCR v2, VAGUE, CLARA) | 15,839 |
| Auxiliary weak pool | `data/processed/schema_v2/weak_pool/weak_pool_auxiliary.jsonl` | auxiliary only (ClariQ) | 8,565 |
| **Total** | | | **24,404** |

TEACh, T13 calibration (`manual:2026:cal:*`), the future manual namespace
(`manual:2026:main/rsv/hb:*`), and the frozen 40-record model-selection set are all
excluded by construction and re-verified by the leakage checks below.

## Outputs

All under `data/development/source_splits_v1/` (tracked path, not committed by this
change):

| Artefact | Purpose |
| --- | --- |
| `record_manifest.jsonl` | One row per record: `id`, `source_dataset`, `source_id`, `pool`, `group_key`, `split`, per-task `eligibility`. |
| `group_manifest.jsonl` | One row per deterministic group: members, split, split-count (must always be 1). |
| `leakage_report.json` | T13/future-manual/model-selection/synthetic-fixture/TEACh checks, all `passed: true`. |
| `coverage_report.json` | Per-split counts, percentages, target percentages, tolerance pass/fail, reconciliation. |
| `eligibility_summary.json` | Per-task counts across `eligible / weakly_eligible / ineligible / unavailable`. |
| `manifest.json` | Top-level programme manifest with counts, notes, and artefact hashes. |
| `hashes.json` | Canonical SHA-256 sidecar for every artefact above. |

Regenerate with:

```bash
python scripts/build_source_data_splits.py
```

## Split policy summary

See `configs/data/source_split_policy_v1.json` for the full policy. Highlights:

- **Seed**: fixed integer `20260722`.
- **Primary target ratios**: `source_train` 70% / `source_dev` 15% / `source_holdout` 15%.
- **Auxiliary target ratios**: `auxiliary_train` 85% / `auxiliary_dev` 15% (ClariQ only; no auxiliary holdout).
- **Tolerance**: ±2.0 percentage points per split.
- **Grouping**: existing `group_id` first, then `id` lineage suffixes (`@<turn>`, `__frame_<n>`)
  for multi-turn/multi-frame context variants, then a normalised-command hash fallback
  so exact/paraphrase duplicates never cross a split.
- **Stratification**: `source_dataset x ambiguity_present bucket`, applied at group
  granularity using each group's lowest-id member as representative.
- **Assignment**: groups are ordered per stratum by `sha256(f"{seed}:{group_key}")` and
  walked once, each time assigning the group to whichever split currently has the
  largest deficit against its stratum target share (a deterministic greedy-proportional
  bin-fill; no dependency on Python's `random` module).

## Realised results (current build)

| Split | Records | Percentage | Target | Deviation (pp) |
| --- | ---: | ---: | ---: | ---: |
| `source_train` | 11,294 | 71.31% | 70.00% | +1.31 |
| `source_dev` | 2,396 | 15.13% | 15.00% | +0.13 |
| `source_holdout` | 2,149 | 13.57% | 15.00% | -1.43 |
| `auxiliary_train` | 7,287 | 85.08% | 85.00% | +0.08 |
| `auxiliary_dev` | 1,278 | 14.92% | 15.00% | -0.08 |

All deviations are within the ±2.0 percentage-point tolerance. Group counts: 6,456
primary groups, 187 auxiliary groups. Coverage reconciles exactly: 24,404 input
records in, 24,404 output records out, no drops and no duplicates.

## Eligibility manifest

Sixteen tasks are scored per record as one of `eligible / weakly_eligible /
ineligible / unavailable` (never a fabricated negative): `structured_training_target`,
`speech_act_intent`, `cpc`, `candidate_interpretations`, `ambiguity_presence_types`,
`compound_ambiguity`, `risk`, `capability`, `route`, `clarification_target`,
`rejection`, `context_blind_pairing`, `uncertainty_sampling`, `adapter_training`,
`source_development_evaluation`, `source_holdout_evaluation`.

Rules are built from the schema-v2 `label_eligibility` flags already attached to
each record by the T09/T10 weak-pool pipeline, refined by whether a concrete value is
present (`eligible`), only a partial/derived signal is present (`weakly_eligible`),
the task is structurally inapplicable for that record's source dataset
(`ineligible`), or the value was simply never collected (`unavailable`). ClariQ is
hard-ineligible for every robot-facing task (route, risk, capability, rejection,
compound ambiguity, adapter training, source evaluation), matching its
auxiliary-only role.

## Leakage checks

`leakage_report.json` reruns five checks against the full 24,404-record pool on
every build:

1. T13 calibration ID overlap (against `annotation/calibration_data.py`, 24 ids/commands).
2. T13 calibration normalised-command overlap.
3. Future manual namespace ID overlap (`manual:2026:main/rsv/hb:*`).
4. Frozen 40-record model-selection set ID and normalised-command overlap.
5. Synthetic evaluator fixture normalised-command overlap (T16-T24 and T12 fixtures).
6. TEACh (or any non-approved) source-dataset presence.

All six currently report zero overlaps (`all_checks_passed: true`).

## Training-target policy

`configs/data/training_target_policy_v1.json` documents **strategy D** (combination
with explicit per-field loss masks): partial-field records are trained, not dropped,
and `unavailable`/`ineligible` fields always carry a `0.0` loss weight so they are
never scored as negatives. `weakly_eligible` fields train at half weight. A 64-record
deterministic QLoRA smoke subset is defined as the seed-ordered prefix of
`source_train`.

## T15 ticket note

`cursor_plan/tickets/T15_gold_splits_leakage_and_eligibility.md` has been annotated to
clarify that this source-development split programme may proceed without T14
adjudicated gold, while the manual protected splits (`manual_protected_challenge_set`)
remain gated on T14C.

## Test evidence

```bash
$env:PYTHONPATH='src'; python -m unittest tests.test_t15_source_splits -v
```

Result: `Ran 25 tests in 5.275s — OK`. Coverage includes deterministic grouping and
rebuild-stability, no-cross-split-group invariants, coverage reconciliation, tolerance
checks, all five leakage families, ClariQ auxiliary-only enforcement, TEACh exclusion,
missing-≠-negative and weak-vs-eligible eligibility semantics, deterministic canonical
hashing, seed recording, the `source_holdout` non-protected-benchmark note, and the
training-target policy mask invariants.

## Limitations

- This is a **weak-label** split; no manual gold is invented or implied anywhere in
  these artefacts.
- `source_holdout` must never be referred to as, or substituted for, the future
  `manual_protected_challenge_set`.
- ClariQ remains auxiliary-only; it is never assigned to `source_train` /
  `source_dev` / `source_holdout`.
