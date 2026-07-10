# CLARA / SaGC -> Canonical Mapping (T07)

- Mapping version: `clara-1.0.0`
- Canonical schema version: `1.0.0`
- Source (authoritative, read-only): `data/raw/CLARA-Dataset/data/agument.json`
- Auxiliary (not used for conversion): `data/sample.json`, `agument.ipynb`

This document records field-level mapping decisions only. No raw goal or scene text
from the dataset is reproduced here; source content is preserved only inside JSONL
conversion outputs.

## Task semantics

SaGC (Situational Awareness for Goal Classification) pairs a robot-type tag,
structured scene lists, and a high-level user command with a coarse uncertainty
label (clear / ambiguous / infeasible). Labels were verified from the local
README, generation notebook, and paper supplementary text — not from numeric
guesswork.

Label 3 (`ignore` in README) is excluded by policy due to semantic conflict
between README, generation prompts, and paper evaluation scope.

## Record-level classification

All converted records are marked:

- `record_class = source_converted`
- `annotation_status = weak_mapped`
- `label_confidence = weak_derived`

## Source label mapping (approved)

| Source `label` | Source semantics | `ambiguity_present` | `capability_status` | `recommended_strategy` |
| --- | --- | --- | --- | --- |
| 0 | clear / certain | `false` | `capable` | `execute` |
| 1 | ambiguous | `true` | `capable` | `clarify` |
| 2 | infeasible | `false` | `unknown` | `null` (abstain) |
| 3 | ignore (conflict) | — | — | **excluded by policy** |

Label 2 combines robot-type mismatch and missing-scene-resource infeasibility;
`incapable` and `face_preserving_rejection` are **not** mapped.

Ambiguity taxonomy subtypes are **abstained** for all labels (`ambiguity_types=[]`,
`primary_ambiguity_type=null`).

## Field mapping

| Canonical field | Source / value | Derivation |
| --- | --- | --- |
| `id` | `clara:{source_index}` | deterministic |
| `record_class` | `source_converted` | fixed |
| `source_dataset` | `clara` | fixed |
| `source_id` | top-level JSON key | non-negative integer string |
| `original_split` | `null` | unsplit corpus |
| `group_id` | `clara:scene:{sha256(scene_json)[:16]}` | hash of deterministic scene JSON |
| `split_status` | `unsplit` | fixed |
| `command` | `goal.strip()` | trimmed for canonical use |
| `scene_context` | `json.dumps(scene, ensure_ascii=False, sort_keys=True, separators=(",", ":"))` | deterministic |
| `dialogue_history` | `[]` | not in source |
| `capability_context` | `Robot type: {task.strip()}` | source-native robot type only |
| `candidate_interpretations` | `[]` | not in source |
| `ambiguity_present` | per label table | weak-derived |
| `ambiguity_types` | `[]` | abstain |
| `primary_ambiguity_type` | `null` | abstain |
| `compound_ambiguity` | `false` | abstain |
| `compound_ambiguity_count` | `0` | abstain |
| `missing_slots` | `[]` | abstain |
| `risk_relevant` | `false` | unsupported |
| `risk_level` | `null` | unsupported |
| `capability_status` | per label table | weak-derived |
| `recommended_strategy` | per label table | weak-derived or abstain |
| `strategy_sequence` | `[]` | unsupported |
| `gold_clarification_question` | `null` | unsupported |
| `clarification_subtype` | `null` | unsupported |
| `resolved_interpretation` | `null` | unsupported |
| `intent` | `null` | unsupported |
| `slots` | `{}` | unsupported |
| `annotation_status` | `weak_mapped` | fixed |
| `label_confidence` | `weak_derived` | fixed |
| `mapping_version` | `clara-1.0.0` | fixed |
| `source_license` | `unresolved` | licence manifest |
| `mapping_notes` | per-record derivation summary | deterministic |
| `source_metadata` | `{source_index, goal, task, label, scene}` verbatim | raw `goal`/`task` preserved |

## Label eligibility

| Flag | L0 | L1 | L2 |
| --- | --- | --- | --- |
| `ambiguity` | true | true | true |
| `clarification_decision` | true | true | true |
| `context_benefit` | true | true | true |
| `routing` | true | true | false |
| `capability` | true | true | false |
| `clarification_target` | false | false | false |
| `rejection` | false | false | false |
| `risk` | false | false | false |
| `intent_slots` | false | false | false |
| `compound_sequence` | false | false | false |

Eligibility indicates a valid evaluation target exists, not that the positive
class applies.

## Exclusion policy (label 3)

| Reason | Treatment |
| --- | --- |
| `source_label_3_semantic_conflict` | Write to `clara_excluded.jsonl`; no canonical record |

## Quarantine reasons

| Reason | Trigger |
| --- | --- |
| `invalid_source_id` | key not a canonical non-negative decimal string (leading zeros rejected) |
| `duplicate_normalized_source_id` | two raw keys normalize to the same ID (raises `ClaraConversionError`) |
| `malformed_record` | wrong keys or non-object record |
| `missing_scene` | scene not exactly `{floorplan, objects, people}` or non-string list items |
| `non_string_goal` | `goal` is not a string |
| `non_string_task` | `task` is not a string |
| `missing_command` | empty `goal` after trim |
| `unknown_label` | label not in `{0,1,2,3}`, not `int`, or boolean |
| `unknown_task` | task not in `{cooking,cleaning,massaging}` |
| `schema_validation_failed` | post-build validation error |

Duplicate top-level JSON object keys raise `ClaraJsonError` at load time.

## Row accounting (actual run)

| Metric | Value |
| --- | ---: |
| Source rows read | 5345 |
| Rows converted | 5222 |
| Rows excluded by policy | 123 |
| Rows quarantined | 0 |
| Rows skipped | 0 |
| Unique output IDs | 5222 |

Per label (converted):

| Label | Count |
| --- | ---: |
| 0 | 1749 |
| 1 | 1560 |
| 2 | 1913 |

Excluded:

| Label | Count | Reason |
| --- | ---: | --- |
| 3 | 123 | `source_label_3_semantic_conflict` |
