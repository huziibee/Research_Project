# VAGUE -> Canonical Mapping (T06)

- Mapping version: `vague-1.0.0`
- Canonical schema version: `1.0.0`
- Source (authoritative, read-only): `data/raw/vague_bench/data/train-00000-of-00001.parquet`
- HuggingFace cache (`data/raw/vague_bench/.cache/**`): **not used**

This document records field-level mapping decisions only. No raw utterance,
caption, or MCQ text from the dataset is reproduced here; source content is
preserved only inside the JSONL conversion output.

## Task semantics

VAGUE (Visual Contexts ClArify ambiGUous Expressions) is a **Multimodal
Intention Disambiguation (MID)** benchmark. Each row pairs an **indirect**
utterance with a scene (image + caption) and four MCQ interpretation options.
The gold NL interpretation (`mcq.1_correct`) and structured action triplet
(`solution`) are source-native labels. The dataset does **not** provide project
ambiguity-taxonomy labels, route labels, or clarification-decision labels.

## Record-level classification

All converted records are marked:

- `record_class = source_converted`
- `annotation_status = weak_mapped`
- `label_confidence = weak_derived`

Source-native gold for intent (`solution`, `mcq.1_correct`) is carried into
canonical fields; the record-level status follows approved weak-mapped policy.

## Ambiguity abstention (approved)

| Field | Value |
| --- | --- |
| `ambiguity_present` | `null` |
| `ambiguity_types` | `[]` |
| `primary_ambiguity_type` | `null` |
| `compound_ambiguity` | `false` |
| `compound_ambiguity_count` | `0` |
| `missing_slots` | `[]` |
| `label_eligibility.ambiguity` | `false` |

Indirect phrasing and dataset name do **not** map to project ambiguity types.

## Field mapping

| Canonical field | Source / value | Derivation |
| --- | --- | --- |
| `id` | `vague:{image_name}` | deterministic |
| `record_class` | `source_converted` | fixed |
| `source_dataset` | `vague` | fixed |
| `source_id` | `image_name` | direct |
| `original_split` | `train` | source-native |
| `group_id` | `null` | approved policy |
| `split_status` | `train` | mapped |
| `command` | `indirect` | source-native benchmark input |
| `scene_context` | `meta.caption` | source-native textual scene |
| `dialogue_history` | `[]` | not in source |
| `capability_context` | `null` | not in source |
| `candidate_interpretations` | four `mcq` option texts in key order | source-native |
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
| `gold_clarification_question` | `null` | unsupported |
| `clarification_subtype` | `null` | unsupported |
| `resolved_interpretation` | `mcq.1_correct` | source-native NL gold |
| `intent` | `solution` (verbatim triplet string) | source-native structured gold |
| `slots` | `{subject, action, object}` from `solution` | deterministic parse |
| `annotation_status` | `weak_mapped` | fixed |
| `label_confidence` | `weak_derived` | fixed |
| `mapping_version` | `vague-1.0.0` | fixed |
| `source_license` | `unresolved` | licence manifest |
| `mapping_notes` | per-record derivation summary | deterministic |
| `source_metadata` | see below | provenance |

## Solution triplet parser

- Strip optional outer parentheses
- Split on commas into exactly three non-empty components
- Map to `slots.subject`, `slots.action`, `slots.object`
- No `eval`, `ast.literal_eval`, or `json.loads` on source values
- Malformed triplets quarantine as `invalid_solution_triplet`
- Original `solution` string preserved verbatim in `source_metadata`

## Image / binary policy

- Parquet column projection excludes `image` entirely
- `image.bytes` never read, materialized, hashed, or serialized
- `image_name` is the stable image reference; no derived `image_path`

## MCQ candidates

`candidate_interpretations` holds four entries in semantic key order:

1. `1_correct`
2. `2_fake_scene`
3. `3_surface_understanding`
4. `4_wrong_entity`

Full `mcq` struct (including `ordering` presentation letters) is preserved in
`source_metadata`. Ordering letters are presentation metadata only.

## Identifier policy

- Register every non-empty `image_name` before row-level quarantine checks
- Duplicate `image_name` raises `VagueConversionError` even if the first row was
  quarantined
- Missing `image_name` quarantines as `missing_source_id`
- `row_index` is provenance metadata only (stored in `source_metadata`)

## Label eligibility

| Flag | Value | Rationale |
| --- | --- | --- |
| `intent_slots` | `true` | `solution` triplet and MCQ options are source gold |
| `context_benefit` | `true` | benchmark designed for with/without-context comparison |
| all others | `false` | no source gold for routing, ambiguity taxonomy, risk, capability, clarification, rejection, or compound sequence |

## Row accounting

Filled by the conversion run in `outputs/metrics/vague_conversion_summary.json`.

Invariant: `source_rows_read == rows_converted + rows_quarantined + rows_skipped`.

## Deferred work

LVLM inference, image-byte processing, train/dev/test split creation, route
policy, ambiguity-taxonomy mapping, register config updates, and experiment
metrics are out of scope for T06.
