# CoDraw-iCR v2 -> Canonical Mapping (T05)

- Mapping version: `codraw_icr_v2-1.0.0`
- Canonical schema version: `1.0.0`
- Source (authoritative, read-only): `data/raw/codraw-icr-v2/codraw-icr-v2.tsv`
- Auxiliary (not used): `data/raw/codraw-icr-v2/codraw-icr-v2_raw.tsv`

This document records field-level mapping decisions only. No raw teller, drawer,
or repair text from the dataset is reproduced here; source content is preserved
only inside the JSONL conversion output.

## Task semantics

CoDraw-iCR v2 annotates **Instruction Clarification Requests (iCRs)** from the
CoDraw collaborative drawing dialogue game. Each authoritative row is a
positive iCR instance: a drawer clarification utterance with local teller
context and content-grounded annotation flags.

The corpus is **not** an instruction-ambiguity or routing gold set. T05 maps
clarification-target gold only.

## Instruction anchoring policy (approved)

A row is converted only when:

- `is_source_utterance_last_turn == "1"`
- `teller_before` is non-empty

Then:

- `command = teller_before`
- `dialogue_history = []`

Otherwise the row is quarantined as `source_instruction_unavailable` (or
`missing_command` when `is_source=1` but `teller_before` is empty).

`teller_after` is **never** copied into canonical fields (future-response
leakage prevention).

## Record-level classification

All converted records are marked:

- `record_class = source_converted`
- `annotation_status = weak_mapped`
- `label_confidence = weak_derived`

`mapping_notes` states that `drawer` and `mood` are source-native, while the
complete canonical record is weak-mapped.

## Ambiguity abstention (approved)

T05 does **not** map CoDraw content flags into project ambiguity taxonomy:

| Field | Value |
| --- | --- |
| `ambiguity_present` | `null` |
| `ambiguity_types` | `[]` |
| `primary_ambiguity_type` | `null` |
| `compound_ambiguity` | `false` |
| `compound_ambiguity_count` | `0` |
| `missing_slots` | `[]` |
| `label_eligibility.ambiguity` | `false` |

Content flags (`position`, `size`, `direction`, `relation_to_other_cliparts`,
`disambig_object`, `disambig_person`) and clipart fields are preserved verbatim
in `source_metadata` as clarification-target annotations only.

## Mood normalization

`clarification_subtype` is derived from `mood`:

- normalize `wh-question` -> `wh- question`
- comma-separated values: split, trim, normalize, deduplicate (preserve order), join with `"; "`
- original `mood` preserved verbatim in `source_metadata`
- unknown mood tokens are retained (not quarantined) and counted as warnings

## Field mapping

| Canonical field | Source / value | Derivation |
| --- | --- | --- |
| `id` | `codraw_icr_v2:{source_index}` | deterministic |
| `record_class` | `source_converted` | fixed |
| `source_dataset` | `codraw_icr_v2` | fixed |
| `source_id` | leading TSV index column | direct |
| `original_split` | `train` / `validation` / `test` | from `game_name` prefix |
| `group_id` | `codraw_icr_v2:game:{game_name}` | deterministic |
| `split_status` | `train` / `dev` / `test` | `val_*` -> `dev` |
| `command` | `teller_before` | anchored instruction |
| `scene_context` | `null` | not synthesized |
| `dialogue_history` | `[]` | fixed |
| `capability_context` | `null` | unsupported |
| `candidate_interpretations` | `[]` | unsupported |
| `ambiguity_present` | `null` | abstain |
| `ambiguity_types` | `[]` | abstain |
| `primary_ambiguity_type` | `null` | abstain |
| `compound_ambiguity` | `false` | abstain |
| `compound_ambiguity_count` | `0` | abstain |
| `missing_slots` | `[]` | abstain |
| `risk_relevant` | `false` | unsupported |
| `risk_level` | `null` | unsupported |
| `capability_status` | `null` | unsupported |
| `recommended_strategy` | `null` | unsupported |
| `strategy_sequence` | `[]` | unsupported |
| `gold_clarification_question` | `drawer` | source-native |
| `clarification_subtype` | normalized `mood` | derived from source |
| `resolved_interpretation` | `null` | not derived from `teller_after` |
| `intent` | `null` | unsupported |
| `slots` | `{}` | unsupported |
| `annotation_status` | `weak_mapped` | fixed |
| `label_confidence` | `weak_derived` | fixed |
| `mapping_version` | `codraw_icr_v2-1.0.0` | fixed |
| `source_license` | `stated_unverified` | licence manifest |
| `mapping_notes` | per-record derivation summary | deterministic |
| `source_metadata` | all 26 source columns verbatim | provenance |

## Label eligibility

| Flag | Value | Rationale |
| --- | --- | --- |
| `clarification_target` | `true` | source `drawer` iCR text |
| all others | `false` | no routing, ambiguity, risk, capability, clarification-decision, context-benefit, intent/slots, rejection, or compound-sequence gold in T05 |

## Quarantine reasons

| Reason | Trigger |
| --- | --- |
| `malformed_row` | field count != header width |
| `missing_source_id` | empty leading index |
| `duplicate_source_id` | repeated source index |
| `missing_clarification_utterance` | empty `drawer` |
| `missing_command` | `is_source=1` and empty `teller_before` |
| `source_instruction_unavailable` | `is_source != 1` or empty `teller_before` |
| `unexpected_non_icr_row` | `is_CR_annotator_2 != 1` |
| `unknown_game_name_prefix` | `game_name` not `train_` / `val_` / `test_` |
| `schema_validation_failed` | post-build validation error |

## Row accounting (actual run)

| Metric | Value |
| --- | ---: |
| Source rows read | 8765 |
| Rows converted | 7034 |
| Rows quarantined | 1731 |
| Rows skipped | 0 |
| Unique output IDs | 7034 |

Per split (converted):

| Split | Converted |
| --- | ---: |
| train | 5604 |
| validation | 726 |
| test | 704 |

Quarantine reasons:

| Reason | Count |
| --- | ---: |
| `source_instruction_unavailable` | 1730 |
| `missing_command` | 1 |

Invariant: `source_rows_read == rows_converted + rows_quarantined + rows_skipped`.

## Deferred work

Ambiguity-type mapping from content flags, `teller_after` resolution gold,
scene synthesis, negative/control mining from raw TSV, split generation, register
config promotion, and experiment metrics are out of scope for T05.
