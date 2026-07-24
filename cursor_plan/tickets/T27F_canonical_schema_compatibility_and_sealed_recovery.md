# T27F — Canonical constrained-schema compatibility and final T27 sealed recovery

## Scope and exclusions

This ticket covers canonical generation-schema authority, exact LMFE 0.10.12 preflight, cluster failure propagation, one development canary, and one fresh source_dev sealed smoke. T28 is prohibited. The immutable base is `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`; adapter/model-selection identities remain null and official use remains false. No protected, source_holdout, calibration, supervisor, manual-gold, or prior sealed data is permitted.

## Frozen contract

- Ambiguity generation is the T27E minimal contract with a 96-token bound.
- Intent speech act is a non-null string enum and is omitted when unsupported.
- Interpretation optional fields are omitted when unsupported; selected interpretation requires unique support.
- Risk and capability are required non-null enums; unavailable values are `unknown`.
- CPC schema, prompt, bound, ownership, and assembly behaviour are unchanged.
- LMFE is exactly 0.10.12, with no unconstrained fallback.

## Execution record

The canonical layer is `src/ambiguity_manager/model/generation_schema.py`, configured by `configs/model/t27f_schema_compatibility_v1.json`. `schema_preflight.py` compiles every effective task using the inference compiler before model loading. Cluster wrappers propagate entry-point status, write `runtime_failure.json` and failed heartbeat state, and require exit code plus expected artifacts for success.

The fresh sealed manifest is `data/development/t27f_final_smoke_v1/manifest.json`. It is source_dev-only, 12 records, round-robin over eligible non-protected datasets, and excludes all listed T27/T27E and model-selection sets. The canary source is T27E diagnostic development data only and is not sealed evidence.

## Stage gate

The gate is BLOCKED unless preflight, canary reconciliation, one fresh sealed run, all required acceptance counts, safety checks, focused/affected tests, and governance checks are committed. T28 may begin only after a human approves a PASS parent T27 transition.
