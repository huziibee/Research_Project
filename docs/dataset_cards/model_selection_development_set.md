# Model Selection Development Set v1

Frozen development-only bake-off set for comparing model-selection pipelines before
protocol freeze. This set is **not** valid for official final claims.

## Status

| Field | Value |
| --- | --- |
| Manifest ID | `model_selection_development_set_v1` |
| Version | `1.0.0` |
| Record count | 40 |
| `manifest_hash` | `70651a6ed5e396235afceb97b8b918e06f0ff742d9a64c15f6444833aaa49cb3` |
| `development_only` | `true` |
| `protected` | `false` |
| `valid_for_official_final_claims` | `false` |

## Purpose

Provide a reproducible, hash-stable development corpus for model-selection experiments
that:

- reuses existing synthetic fixtures instead of unpublished interim schema-v2 data
- excludes T13 calibration records (`manual:2026:cal:0001-0024`)
- excludes future manual main/rsv/hb namespaces
- marks missing or route-pressure-only labels as metric-ineligible
- keeps all records out of the future manual challenge pool

## Sources

| Source | Count | Gold |
| --- | ---: | --- |
| `tests/fixtures/t16_t24_synthetic/` | 16 | Full adjudicated synthetic gold |
| `tests/fixtures/schema_v2/t12_synthetic_inputs.jsonl` | 10 | Route pressure only; no invented gold |
| Hand-authored `msel_dev_*` records | 14 | Author-provided gold only where declared |

## Layout

- Experiment config: `configs/experiments/model_selection_development_set_v1.json`
- Dataset directory: `data/development/model_selection_v1/`
- Builder: `scripts/build_model_selection_development_set.py`
- Loader: `src/ambiguity_manager/data/model_selection_set.py`

## Transport smoke subset

Four frozen IDs in `transport_smoke_ids.json`, adapted from dfinal-style schema-v2
fixtures:

- `msel_t12_syn_001` — execute pressure
- `msel_t12_syn_002` — clarify pressure
- `msel_t12_syn_003` — silently_resolve pressure
- `msel_t12_syn_005` — multi_step pressure

## Regeneration

```bash
python scripts/build_model_selection_development_set.py
```

The builder prints the canonical `manifest_hash` after rewriting all artefacts.

## Quality controls

Each build emits:

- exact and normalized duplicate detection (context-benefit pair intentionally shares command text)
- calibration-ID overlap check (must be empty)
- future manual-ID namespace separation
- coverage and eligibility summaries
- unsupported-label audit comparing declared vs observed gold fields

## Tests

```bash
python -m unittest tests.test_model_selection_development_set -v
```

## Limitations

- Route-pressure rows from schema-v2 fixtures carry no intent/CPC/route/risk/capability gold.
- One hand-authored record (`msel_dev_no_gold_labels`) is fully metric-ineligible.
- Do not use this set for protected-data evaluation or official result reporting.
