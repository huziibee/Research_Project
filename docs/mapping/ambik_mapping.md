# AmbiK -> Canonical Mapping (T03)

- Mapping version: `ambik-1.0.0`
- Canonical schema version: `1.0.0`
- Source (authoritative, read-only): `data/raw/AmbiK/AmbiK_data.csv`
- Source SHA-256: `98bb4677eb7fad00a58393aa751f833c5e01dcda9090fe0ef202272b20e2f531`
- Auxiliary AmbiK CSVs: **not used** in T03.

This document records field-level mapping decisions only. No raw command,
question, answer, or plan text from the dataset is reproduced here; source
content is preserved only inside the JSONL conversion output.

## Record-level classification

The AmbiK ambiguity categories and clarification text are source-native, but the
canonical ambiguity taxonomy labels are **deterministic mappings** into the
frozen project taxonomy. Therefore every converted record is marked:

- `record_class = source_converted`
- `annotation_status = weak_mapped`
- `label_confidence = weak_derived`

These are mapped-source labels, **not** manually adjudicated gold.

## Ambiguity-type mapping

AmbiK provides exactly one coarse category per row. Each maps to a single
canonical ambiguity type. No compound (multi-type) ambiguity is inferred.

| Source `ambiguity_type` | Canonical label | Rows | Confidence | Notes |
| --- | --- | ---: | --- | --- |
| `preferences` | `preference` | 420 | high | Choice among interchangeable objects. |
| `common_sense_knowledge` | `commonsense` | 425 | high | World/domain knowledge needed to interpret. |
| `safety` | `safety_precondition` | 155 | high (approved) | Safety-relevant ambiguity; sets `risk_relevant=true` only. |

Unknown / unmapped `ambiguity_type` values are quarantined
(`unknown_ambiguity_type`); they are never guessed.

## Field mapping

| Canonical field | Source / value | Derivation |
| --- | --- | --- |
| `id` | `ambik:{id}` | deterministic |
| `record_class` | `source_converted` | fixed |
| `source_dataset` | `ambik` | fixed |
| `source_id` | `id` | direct |
| `original_split` | `null` | primary CSV is unsplit |
| `group_id` | `ambik:group:{id}` | deterministic |
| `split_status` | `unsplit` | fixed |
| `command` | `ambiguous_task` | direct (exact string) |
| `scene_context` | `environment_full` | direct (exact string) |
| `dialogue_history` | `[]` | not in source |
| `capability_context` | `null` | not in source |
| `ambiguity_present` | `true` | structural (all rows are ambiguous tasks) |
| `ambiguity_types` | `[mapped type]` | deterministic mapping |
| `primary_ambiguity_type` | mapped type | deterministic |
| `compound_ambiguity` | `false` | single source label |
| `compound_ambiguity_count` | `1` | schema invariant |
| `missing_slots` | `[]` | no structured slots in source |
| `risk_relevant` | `true` iff `safety_precondition`; else `false` | boolean flag only |
| `risk_level` | `null` | not provided by source |
| `capability_status` | `null` | not provided by source |
| `recommended_strategy` | `null` | no route label in source |
| `strategy_sequence` | `[]` | no route sequence in source |
| `gold_clarification_question` | `question` | mapped-source clarification target |
| `clarification_subtype` | `null` | not in source |
| `resolved_interpretation` | `unambiguous_direct` | source-native paired resolution |
| `intent` | `null` | `user_intent` is token-like, not NL intent |
| `slots` | `{}` | not fabricated |
| `annotation_status` | `weak_mapped` | see record-level classification |
| `label_confidence` | `weak_derived` | see record-level classification |
| `mapping_version` | `ambik-1.0.0` | fixed |
| `source_license` | `unresolved` | from licence manifest |
| `mapping_notes` | per-record mapping description | deterministic |
| `source_metadata` | all 15 source columns, verbatim strings | provenance preservation |

## Label eligibility

| Flag | Value | Rationale |
| --- | --- | --- |
| `ambiguity` | `true` | mapped-source ambiguity label |
| `clarification_target` | `true` | source clarification question present on every row |
| all others | `false` | no source gold for routing, risk, capability, clarification decision, intent/slots, rejection, compound sequence, or context benefit |

`ambiguity` and `clarification_target` are enabled as **mapped-source** labels,
not manually adjudicated gold.

## List-like source fields

`variants`, `amb_shortlist`, `user_intent`, `plan_for_clear_task`, and
`plan_for_amb_task` are preserved as **raw source strings** in
`source_metadata`. T03 does not parse them into structured canonical fields and
never applies `eval`, `ast.literal_eval`, or `json.loads` to source values.

## Row accounting (actual run)

| Metric | Value |
| --- | ---: |
| Source rows read | 1000 |
| Rows converted | 1000 |
| Rows skipped | 0 |
| Rows quarantined | 0 |
| Unique output IDs | 1000 |

Invariant: `source_rows_read == rows_converted + rows_skipped + rows_quarantined`.
Output ordering is deterministic by numeric `source_id` ascending.

## Deferred work

Splits, weak-pool assembly, manual annotation, routing/risk/capability labels,
auxiliary CSV integration, and experiment metrics are out of scope for T03.
