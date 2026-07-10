# IndirectRequests -> Canonical Mapping (T04)

- Mapping version: `indirect_requests-1.0.0`
- Canonical schema version: `1.0.0`
- Source (authoritative, read-only):
  - `data/raw/IndirectRequests/train/data-00000-of-00001.arrow`
  - `data/raw/IndirectRequests/validation/data-00000-of-00001.arrow`
  - `data/raw/IndirectRequests/test/data-00000-of-00001.arrow`
- Container: HuggingFace **Arrow IPC stream** (`pyarrow.ipc.open_stream` only)

This document records field-level mapping decisions only. No raw utterance,
situation, or paraphrase text from the dataset is reproduced here; source
content is preserved only inside the JSONL conversion output.

## Task semantics

IndirectRequests provides **indirect user utterances** in schema-guided
task-oriented dialogue. Each row includes a crowd-labelled
`target_slot_value` (concrete slot gold or the sentinel `<ambiguous>`) and a
`mean_world_understanding` difficulty rating. Indirect phrasing is universal in
the corpus; **ambiguity** is labelled only when `target_slot_value` is
`<ambiguous>`.

## Record-level classification

All converted records are marked:

- `record_class = source_converted`
- `annotation_status = weak_mapped`
- `label_confidence = weak_derived`

Slot values on concrete-target rows are source-native gold carried into
`slots`, but the record-level status reflects approved weak-mapped policy for
the whole corpus.

## Ambiguity mapping

| Source `target_slot_value` | `ambiguity_present` | `ambiguity_types` | `primary_ambiguity_type` |
| --- | --- | --- | --- |
| `<ambiguous>` | `true` | `[pragmatic]` | `pragmatic` |
| any other non-empty string | `false` | `[]` | `null` |

Indirectness alone does **not** imply ambiguity. No route, risk, capability,
or compound ambiguity labels are inferred.

## Field mapping

| Canonical field | Source / value | Derivation |
| --- | --- | --- |
| `id` | `indirect_requests:{split}:{row_index}` | deterministic |
| `record_class` | `source_converted` | fixed |
| `source_dataset` | `indirect_requests` | fixed |
| `source_id` | `{split}:{row_index}` | deterministic |
| `original_split` | `train` / `validation` / `test` | source-native |
| `group_id` | `null` | no pairing inferred from `creation_date` |
| `split_status` | `train` / `dev` / `test` | mapped from `original_split` |
| `command` | `utterance` | source-native |
| `scene_context` | `situation` | source-native |
| `dialogue_history` | `[]` | not in source |
| `capability_context` | `null` | `service` is schema domain, not capability |
| `candidate_interpretations` | `[]` | not parsed from serialized lists |
| `ambiguity_present` | from `target_slot_value` | deterministic |
| `ambiguity_types` | see ambiguity table | weak-derived when ambiguous |
| `primary_ambiguity_type` | see ambiguity table | weak-derived when ambiguous |
| `compound_ambiguity` | `false` | no multi-type evidence |
| `compound_ambiguity_count` | `1` if ambiguous; else `0` | schema invariant |
| `missing_slots` | `[slot_description]` if ambiguous; else `[]` | weak-derived |
| `risk_relevant` | `false` | not in source |
| `risk_level` | `null` | not in source |
| `capability_status` | `null` | not in source |
| `recommended_strategy` | `null` | not in source |
| `strategy_sequence` | `[]` | not in source |
| `gold_clarification_question` | `null` | not in source |
| `clarification_subtype` | `null` | not in source |
| `resolved_interpretation` | `null` | T04 policy: never populated |
| `intent` | `null` | no NL intent string in source |
| `slots` | `{slot_description: target_slot_value}` if concrete; else `{}` | source-native slot gold |
| `annotation_status` | `weak_mapped` | approved O1 |
| `label_confidence` | `weak_derived` | approved O1 |
| `mapping_version` | `indirect_requests-1.0.0` | fixed |
| `source_license` | `unresolved` | licence manifest |
| `mapping_notes` | per-record derivation summary | deterministic |
| `source_metadata` | all 9 source columns verbatim | provenance preservation |

## Label eligibility

| Flag | Value | Rationale |
| --- | --- | --- |
| `intent_slots` | `true` | only when `target_slot_value` is concrete (non-`<ambiguous>`) |
| `ambiguity` | `true` | only on `<ambiguous>` rows |
| all others | `false` | no source gold for routing, risk, capability, clarification, rejection, compound sequence, or context benefit |

## Open-vocabulary target policy

`target_slot_value` is treated as open vocabulary:

- null or empty -> quarantine (`missing_target_slot_value`)
- exactly `<ambiguous>` -> ambiguous row handling
- any other non-empty string -> concrete slot gold (never quarantined for novelty)

## Serialized list fields

`possible_slot_values` and `bool_rephrased_slot_values` are preserved as **raw
source strings** in `source_metadata`. T04 does not parse them and never uses
`eval`, `ast`, or `json.loads` on source values. `bool_rephrased_slot_values`
is **not** used to populate `resolved_interpretation`.

## Row accounting (actual run)

| Metric | Value |
| --- | ---: |
| Source rows read | 906 |
| Rows converted | 906 |
| Rows skipped | 0 |
| Rows quarantined | 0 |
| Ambiguous rows | 162 |
| Concrete-target rows | 744 |
| Unique output IDs | 906 |

Per split:

| Split | Rows read | Converted | Ambiguous | Concrete |
| --- | ---: | ---: | ---: | ---: |
| train | 246 | 246 | 44 | 202 |
| validation | 272 | 272 | 42 | 230 |
| test | 388 | 388 | 76 | 312 |

Invariant: `source_rows_read == rows_converted + rows_skipped + rows_quarantined`.
Ordering: `train`, then `validation`, then `test`, each by ascending `row_index`.

## Deferred work

Weak-pool assembly, register config promotion, licence verification, parsing
candidate lists into `candidate_interpretations`, `mean_world_understanding`
evaluation use, cross-split utterance-text deduplication policy, and experiment
metrics are out of scope for T04.
