# ClariQ -> Canonical Mapping (T08)

- Mapping version: `clariq-1.0.0`
- Canonical schema version: `1.0.0`
- Source (authoritative, read-only): `data/raw/ClariQ/data/train.tsv`
- Role: **auxiliary** clarification-style data; never robot-domain gold

This document records field-level mapping decisions only. No raw requests,
questions, answers, topic descriptions, or facet descriptions are reproduced
here; source content is preserved only inside conversion output artefacts.

## Why ClariQ is auxiliary

ClariQ (ConvAI3) targets open-domain information-seeking clarification: an
underspecified user request, optional clarifying question, and simulated user
answer. It is not embodied, scene-grounded, or robot-command specific. It may
support auxiliary clarification-target supervision only.

## Task semantics

Each authoritative `train.tsv` row is one **positive relevant clarifying
question** for a topic/facet information need, unless `question_id=Q00001`
(no-question marker).

Official ClariQ subtasks (README + `clariq_eval_tool.py`):

| Subtask | Source signal | Used in T08 canonical? |
| --- | --- | --- |
| Clarification need (ordinal 1–4) | `clarification_need` per `topic_id` | Metadata only |
| Question relevance | Rows list relevant questions per topic | Drives `gold_clarification_question` |
| Document relevance | `*.qrel` + eval pickles | **Not used** |

Pre-implementation audit (read-only, not opened by converter): all train
`question_id` values exist in `question_bank.tsv` with matching question text
(0 missing, 0 mismatches). T08 does not re-check the bank at conversion time.

## Files not opened by converter

- `dev.tsv`, `test.tsv`, `test_with_labels.tsv`
- `question_bank.tsv`
- `*.qrel`
- `multi_turn_human_generated_data.tsv`
- eval pickles and synthetic multi-turn data

## Record granularity

One canonical record per convertible `train.tsv` row after accounting precedence:

1. Validate identifiers and required fields
2. Compute stable full-row SHA-256 source ID
3. Quarantine exact duplicate rows (`duplicate_exact_row`)
4. Exclude unique `Q00001` rows (`source_no_question_marker`)
5. Convert remaining valid rows

Conflicting composite keys `(topic_id, facet_id, question_id)` with different
full-row content each produce a distinct canonical record (no first-wins).

## Source ID policy

```
full_row_sha256 = SHA-256(JSON(sorted nine TSV fields))
source_id = train:{topic_id}:{facet_id}:{question_id}:{full_row_sha256}
id = clariq:{source_id}
```

`source_row_index` is provenance only; it is not part of the fingerprint.

## Group and split policy

| Field | Value |
| --- | --- |
| `original_split` | `train` |
| `group_id` | `clariq:topic:{topic_id}` |
| `split_status` | `unsplit` |

T08 does not assign project train/dev/test splits.

## Record-level classification

| Field | Value |
| --- | --- |
| `record_class` | `source_converted` |
| `annotation_status` | `weak_mapped` |
| `label_confidence` | `weak_derived` |
| `mapping_notes` | `auxiliary_non_robotic_clarification` |

## Abstention policy (approved)

| Field | Value |
| --- | --- |
| `ambiguity_present` | `null` |
| `ambiguity_types` | `[]` |
| `primary_ambiguity_type` | `null` |
| `recommended_strategy` | `null` |
| `strategy_sequence` | `[]` |
| `resolved_interpretation` | `null` |
| `intent` | `null` |
| `slots` | `{}` |
| `scene_context` | `null` |
| `capability_context` | `null` |
| `risk_level` | `null` |

## Label eligibility (converted rows)

| Flag | Value |
| --- | --- |
| `clarification_target` | `true` |
| `clarification_decision` | `false` |
| `routing` | `false` |
| `ambiguity` | `false` |
| `risk` | `false` |
| `capability` | `false` |
| `intent_slots` | `false` |
| `rejection` | `false` |
| `compound_sequence` | `false` |
| `context_benefit` | `false` |

`clarification_need` is ordinal topic-level metadata; it is not mapped to binary
project clarification-decision gold.

## Field mapping

| Canonical field | Source / value | Derivation |
| --- | --- | --- |
| `command` | `initial_request` (trimmed) | source-native text |
| `gold_clarification_question` | `question` (trimmed, non-empty) | source-native |
| `group_id` | `clariq:topic:{topic_id}` | deterministic |
| `source_metadata.*` | all nine TSV columns verbatim | source-native |
| `source_metadata.source_row_index` | TSV line number | provenance |

## Q00001 exclusion policy

Rows with `question_id=Q00001` are excluded to `clariq_excluded.jsonl` with
reason `source_no_question_marker`. They do not become canonical records.
Exact duplicate `Q00001` rows are quarantined before exclusion precedence
applies to the duplicate occurrence.

## Negative-candidate policy

Implicit question-bank negatives are **not** materialized. qrel document
relevance is **not** conversion input.

## Quarantine reasons

| Reason | Trigger |
| --- | --- |
| `malformed_row` | TSV column width mismatch |
| `invalid_topic_id` | non-decimal or empty |
| `invalid_facet_id` | not `F[0-9]+` |
| `invalid_question_id` | not `Q[0-9]+` |
| `unknown_clarification_need` | not in `{1,2,3,4}` |
| `missing_initial_request` | empty after trim |
| `missing_question` | empty for non-`Q00001` |
| `duplicate_exact_row` | identical full-row fingerprint seen earlier |
| `schema_validation_failed` | canonical validation error |

Topic-level conflicting `clarification_need` values raise `ClariqConsistencyError`
before outputs are written.

## Row accounting (actual run)

| Metric | Count |
| --- | ---: |
| `source_rows_read` | 9176 |
| `rows_converted` | 8565 |
| `rows_excluded_by_policy` | 610 |
| `rows_quarantined` | 1 |
| `rows_skipped` | 0 |

Duplicate evidence:

| Metric | Count |
| --- | ---: |
| `composite_collision_groups` | 17 |
| `rows_in_composite_collision_groups` | 34 |
| `exact_duplicate_groups` | 1 |
| `exact_duplicate_rows_beyond_first` | 1 |
| `conflicting_composite_groups` | 16 |
| `distinct_rows_in_conflicting_composite_groups` | 32 |
| `raw_q00001_rows` | 610 |
| `unique_q00001_rows_excluded` | 610 |

Invariant: `9176 = 8565 + 610 + 1 + 0`.

## Output artefacts

| Path | Purpose |
| --- | --- |
| `data/interim/clariq/clariq_canonical.jsonl` | Canonical auxiliary records |
| `data/interim/clariq/clariq_quarantine.jsonl` | Malformed/duplicate rows |
| `data/interim/clariq/clariq_excluded.jsonl` | `Q00001` policy exclusions |
| `outputs/metrics/clariq_conversion_summary.json` | Machine-readable accounting |

## Limitations

- Auxiliary only; not core robot ambiguity benchmark gold.
- Licence status remains `unresolved`.
- No project split assignment in T08.
- No ambiguity-taxonomy or routing labels inferred.
- `answer` preserved as metadata only; not `resolved_interpretation`.
