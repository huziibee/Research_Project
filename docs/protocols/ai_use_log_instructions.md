# Generative AI Use Log Instructions

## Location

Append-only log: `docs/governance/logs/generative_ai_use_log.jsonl`

Governance evidence logs are version-controlled under `docs/governance/logs/`.
Runtime experiment logs may use `outputs/logs/` in later tickets.

## Entry rules

- Append only; never edit or delete prior rows.
- Corrections require a new entry referencing `supersedes_entry_id`.
- Use `use_categories` as a non-empty list of unique allowed categories.
- Record tools in the structured `tools` list; do not invent model revisions.
- Distinguish `activity_period`, `recorded_at`, and `historical_backfill`.
- Protected data must not appear in external AI tool inputs unless an
  authorization reference exists.

## Allowed use categories

`planning`, `coding`, `debugging`, `data_authoring`, `annotation_support`,
`model_inference`, `analysis`, `writing`

## Disclosure

T37 exports a disclosure appendix from entries with `disclosure_category` other
than `none`.
