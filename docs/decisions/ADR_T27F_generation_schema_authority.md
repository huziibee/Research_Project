# ADR T27F: canonical generation-schema authority

## Status

Accepted for T27F technical recovery; official-use selection remains blocked until the sealed gate passes.

## Decision

The production `StructuredAnalysis` schema and the model-generation schema are distinct contracts. `configs/model/task_conditioned_prediction_tasks_v1.json` remains the semantic production source. `src/ambiguity_manager/model/generation_schema.py` derives one versioned LMFE-compatible registry from it, and every training, prompt, diagnostic, smoke, sealed, preflight, and future T28 entry point loads that registry through `load_task_registry`.

Optional model properties are omitted when unsupported; the deterministic assembler may represent their absence as production `null`. Required prediction fields use explicit `unknown` values where information is unavailable. No missing information is converted into a safe value, a capable value, or `ambiguity_present=false`.

The proven T27E ambiguity generation contract is promoted: only `ambiguity_present` and `ambiguity_types` are generated, with the frozen 96-token limit. `primary_ambiguity_type` and `unresolved_slots` remain production-owned fields and are not generated. CPC is unchanged and its effective schema hash is invariant.

The exact LMFE 0.10.12 parser path is run by a fail-fast preflight before model or adapter loading. Unconstrained fallback is forbidden. Schema hashes and prompt identities are recorded in evidence.

## Consequences

The assembler remains responsible for deterministic normalisation and fail-safe routing. A schema compatibility defect blocks execution before GPU-heavy work. T28 must use the same generation-schema version and task hashes; it may not reintroduce ticket-local schema monkey patches.
