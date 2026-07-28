# T28-R1 handover

T28-R1 is **BLOCKED** after successful technical recovery of the existing frozen join.

Recovered artifacts:

- canonical primary pool: `data/processed/weak_pool/weak_pool_canonical.jsonl`
- canonical SHA-256: `1e51cac046e014a6b890b10a155d22e32e01aa276d4507a10ad4f86abcf9942a`
- permitted train/dev view: `data/processed/weak_pool/t28_permitted_train_dev.jsonl`
- permitted view SHA-256: `34b551c37c8f97c24c1263a2cc12a9497e65f754924f1404c47055999f04ea22`

The view contains 11,294 frozen `source_train` and 2,396 frozen `source_dev` records. It contains no `source_holdout`, protected, manual, TEACh, or smoke-only substitution. The join, group-disjointness, deterministic serialization, provenance fields, and CPU task-target canary passed.

The acceptance gate is blocked because the authoritative dataset licence register has unresolved/unverified identifiers and permissions for the included sources. No licence was fabricated. No training occurred; `selected_adapter` and `selected_model_strategy` remain null; `valid_for_official_use` remains false; T29 did not begin.

Do not resume T28 training until the licence/provenance dependency is resolved and a separate human approval is recorded. Do not begin T29.
