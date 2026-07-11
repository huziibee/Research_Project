# T12 Stage D1A — Schema-v2 Prompt and Ownership Contracts (Hardened)

**Stage:** D1A (contracts only; no structured decoding)
**Branch:** `feature/t12-cluster-redesign`
**Starting SHA:** `59e766f7309800780f7d41dd09848127f0da8f64`
**Date:** 2026-07-11
**Governance:** DEV-20260711-001 (synthetic-only preparatory work; T11 remains BLOCKED)

## Scope

Stage D1A delivers CPU-only contracts for:

- canonical schema-v2 field ownership;
- programmatic model-facing semantic schema derivation with strict required-field contract;
- standards-compliant JSON Schema validation (`jsonschema` Draft 2020-12);
- deterministic full-record assembly with semantic round-trip guard;
- prompt message contract using only `system` and `user` roles;
- frozen schema and prompt hashes;
- bounded-attempt generation policy contract;
- fail-closed response-mode verification interface;
- explicit runner-owned `label_eligibility` and prediction-provenance policy;
- acceptance-rule identifiers (no T19 router).

## Non-scope

- structured JSON decoding / vLLM guided decoding (Stage D1B+);
- Qwen3 chat-template rendering or thinking-mode verification;
- model regeneration pipeline;
- batch runner or vLLM backend changes;
- full `route_policy_gate.py` / T19 routing;
- cluster, SSH, Slurm, Apptainer, model, or tokenizer execution;
- prediction-specific provenance enum members in schema-v2 (deferred before official experiments).

## Red probe: silent default insertion (pre-hardening)

Before corrections, `validate_semantic_payload()` and `assemble_prediction_record()` accepted malformed model output that relied on dataclass defaults:

| Probe | Pre-hardening result |
|---|---|
| `{"label_eligibility": {}, "cpc": {}}` | ACCEPTED |
| `{"cpc": {}}` only | ACCEPTED |
| Missing CPC slot | ACCEPTED |
| CPC slot missing `value` | ACCEPTED |
| CPC slot missing `status` | ACCEPTED |
| Extra CPC slot | ACCEPTED |
| Extra CPC slot property | ACCEPTED |
| Evidence missing `source` | ACCEPTED |
| Extra evidence property | ACCEPTED |
| Partial `label_eligibility` flags | ACCEPTED |
| Unknown eligibility flag | ACCEPTED |
| Assemble with empty `cpc` | ACCEPTED |

These defects are now covered by red tests in `tests/test_t12_prediction_contract.py::T12RedProbeSilentDefaultDefects` and fail after hardening.

## Authoritative schema source

Python schema-v2 definitions remain authoritative:

- `src/ambiguity_manager/schema/v2/taxonomies.py`
- `src/ambiguity_manager/schema/v2/records.py`
- `src/ambiguity_manager/schema/v2/validation.py`
- `src/ambiguity_manager/schema/v2/json_schema.py` (`build_prediction_json_schema()`)

The checked-in semantic artefact is derived; it is not an independent source of truth.

## Complete field-ownership matrix

| Field | Ownership | Rationale |
|---|---|---|
| `schema_version` | runner_owned | Fixed from `SCHEMA_VERSION` code constant |
| `id` | runner_owned | Caller request ID is canonical |
| `record_class` | runner_owned | Always `prediction` for T12 inference |
| `source_dataset` | runner_owned | Caller/synthetic source identity |
| `source_id` | runner_owned | Caller provenance |
| `original_split` | runner_owned | Caller provenance |
| `group_id` | runner_owned | Caller provenance |
| `split_status` | runner_owned | Caller/runtime split assignment |
| `command` | runner_owned | Copied byte-for-byte from caller input |
| `scene_context` | runner_owned | Caller input context |
| `dialogue_history` | runner_owned | Caller input context |
| `capability_context` | runner_owned | Caller input context |
| `annotation_status` | runner_owned | Applied from explicit `PredictionProvenancePolicy` |
| `label_confidence` | runner_owned | Applied from explicit `PredictionProvenancePolicy` |
| `migration_version` | runner_owned | Null for native predictions |
| `migrated_from_schema_version` | runner_owned | Null for native predictions |
| `v1_legacy` | runner_owned | Null for native predictions |
| `mapping_version` | runner_owned | Caller provenance |
| `source_license` | runner_owned | Caller provenance |
| `mapping_notes` | runner_owned | Caller provenance |
| `source_metadata` | runner_owned | Caller provenance |
| `prediction_metadata` | assembled_or_derived | Runtime merges model_id, prompt_hash, seed, raw output |
| `label_eligibility` | runner_owned | Metric denominators; explicit runner supply via `PredictionRequestContext`; T15 will enforce experiment eligibility |
| `cpc` | model_owned | Required semantic structure |
| `speech_act` | model_owned | Semantic analysis |
| `intent_summary` | model_owned | Semantic analysis |
| `candidate_interpretations` | model_owned | Semantic analysis |
| `selected_interpretation` | model_owned | Semantic analysis |
| `unresolved_slots` | model_owned | Semantic analysis |
| `supporting_evidence` | model_owned | Semantic analysis |
| `ambiguity_present` | model_owned | Semantic analysis |
| `ambiguity_types` | model_owned | Semantic analysis |
| `primary_ambiguity_type` | model_owned | Semantic analysis |
| `compound_ambiguity` | model_owned | Semantic analysis |
| `compound_ambiguity_count` | model_owned | Semantic analysis |
| `risk_relevant` | model_owned | Semantic analysis |
| `risk_level` | model_owned | Required non-null when runner `label_eligibility.risk` is true |
| `capability_status` | model_owned | Required non-null when runner `label_eligibility.capability` is true |
| `recommended_strategy` | model_owned | Semantic route proposal (T19 remains final authority) |
| `strategy_sequence` | model_owned | Required for `multi_step` |
| `clarification_question` | model_owned | Required for `clarify` |
| `clarification_subtype` | model_owned | Semantic analysis |
| `clarification_targets` | model_owned | Required for `clarify` |
| `rejection_reason` | model_owned | Required for `face_preserving_rejection` |
| `resolved_slots` | model_owned | Required for `silently_resolve` |
| `resolution_method` | model_owned | Required for `silently_resolve` |
| `resolution_evidence` | model_owned | Required for `silently_resolve` |
| `context_sampling_uncertainty` | model_owned | Optional semantic uncertainty |

Contract validation: every canonical prediction property is classified exactly once; no overlap; no omission.

## Schema derivation

- **Derivation version:** `t12-d1a-1.1.0`
- **Method:** start from `build_prediction_json_schema()`, deep-copy all model-owned properties and definitions, remove runner-owned and assembled fields, require every model-owned top-level key, encode route conditionals with standard JSON Schema `allOf`/`if`/`then`, retain `additionalProperties: false`.
- **Canonical prediction schema hash:** `7e33492eda7edce7623ff4590f8544ad9464613b558cb8f3fd72950a26ba43e0`
- **Model semantic schema hash:** `232235fec53ee38eafcd714fd53664b250e848a6b0f75fca1ff7ec903b08cfb4`
- **Checked-in artefact:** `configs/model/schema/t12_model_semantic_output.schema.json` (byte-identical to runtime derivation)

## Model-output required-field contract

`MODEL_OUTPUT_REQUIRED_FIELDS` equals the complete set of model-owned fields (25 keys). The model must emit every key explicitly; null and empty-array values are permitted only where the canonical schema allows them. Omitted keys fail before dataclass parsing.

## Strict nested validation

1. `validate_semantic_payload()` rejects unknown keys, runner-owned keys (including model-supplied `label_eligibility`), and missing required top-level model fields.
2. `jsonschema.Draft202012Validator` validates the payload against the generated model-facing schema (CPC slots, evidence objects, enums, route conditionals, `additionalProperties: false`).
3. Post-schema Python rules enforce cross-field constraints not fully expressible in JSON Schema (documented in evidence contract).
4. After assembly, a semantic round-trip guard compares model-owned fields in the final record against the validated payload and rejects silent insertion, deletion, or coercion.

Declared dependency: `jsonschema>=4.0` in `pyproject.toml`.

## Enforceable JSON Schema route conditionals

Encoded in `allOf` with `if`/`then`:

1. `silently_resolve` → non-empty `resolved_slots`, non-empty `resolution_method`, non-empty `resolution_evidence`
2. `clarify` → non-empty `clarification_targets`, non-empty `clarification_question`
3. `face_preserving_rejection` → non-empty `rejection_reason`
4. `multi_step` → `strategy_sequence` with at least two items
5. any route other than `multi_step` → empty `strategy_sequence`

Custom `route_conditional_requirements` metadata was removed from the schema; derivation metadata lives in the evidence contract only.

## Assembler contract

`assemble_prediction_record(request_context, semantic_payload, runtime_metadata, provenance_policy)`:

1. requires explicit runner `label_eligibility` on `PredictionRequestContext`;
2. validates semantic payload strictly (no model eligibility or provenance fields);
3. merges runner context, runner eligibility, provenance policy values, and runtime metadata;
4. validates through existing `validate_canonical_record_v2()`;
5. enforces semantic round-trip equality for model-owned fields;
6. never returns an invalid record.

## Prediction provenance policy

`PredictionProvenancePolicy` (explicit runner input):

- `policy_version`: `t12-d1a-synthetic-placeholder-1.0.0`
- `annotation_status`: `weak_mapped` (existing schema-v2 enum; not a new member)
- `label_confidence`: `weak_derived` (existing schema-v2 enum; not a new member)
- `explanation`: documents that current values are synthetic placeholders, not human annotation provenance

**Limitation:** schema-v2 has no prediction-specific provenance enum values. Official experiment provenance must be resolved before protected runs.

Default policy: `default_synthetic_prediction_provenance_policy()`.

## Prompt construction

- **Template:** `configs/model/prompts/t12_schema_v2_system.md`
- **Builder:** `src/ambiguity_manager/model/prompt_builder.py`
- **Messages:** `system` and `user` only (no custom `context` role)
- **User message:** deterministic labelled sections `[ORIGINAL_COMMAND]`, optional `[SCENE_CONTEXT]`, `[DIALOGUE_HISTORY]`, `[CAPABILITY_CONTEXT]`
- **System message:** complete compact model-facing JSON Schema text (no Markdown fences), schema hash, runner-owned field exclusion rule
- **Deterministic prompt hash:** SHA-256 over canonical JSON message list
- **No** Qwen chat-template rendering, runtime parameter guesses, torch/transformers/vLLM imports

## Response-mode status

- **Status:** `unverified_until_pinned_runtime_inspection`
- **Interface:** `src/ambiguity_manager/model/response_mode.py`
- **Fail-closed:** `require_generation_ready()` raises while status is not `verified`
- D1A does **not** claim a verified chat-template or thinking-mode method

## Attempt and repair policy

From `configs/model/t12_generation_policy.json`:

| Parameter | Value |
|---|---|
| Total model attempts | 3 |
| Initial generation | 1 |
| Bounded regeneration | 2 |
| Local JSON repair rounds | 2 (matches `MAX_REPAIR_ROUNDS`) |
| Unconstrained fallback | false |
| Retain all raw attempts | true |
| Structural vs semantic metrics | separate |
| Accept schema-invalid output | false |
| Exhausted attempts | explicit rejection |
| Silent enum coercion | false |
| Field invention | false |

## T19 boundary

D1A defines acceptance-rule identifiers only. No new routing precedence or tie-breaking was implemented.

## No-model / no-cluster statement

No SSH, Slurm, Apptainer, vLLM, model weights, or tokenizer were accessed. All validation was CPU-only local unit testing.

## Tests and results

```text
python -m unittest tests.test_t12_prediction_contract -v   → OK (54)
python -m unittest tests.test_t12_prompt_builder -v        → OK (19)
python -m unittest tests.test_t12_response_mode -v         → OK (7)
python -m unittest tests.test_t12_generation_policy -v     → OK (11)
python -m unittest discover -s tests -p "test_t12_*.py"    → OK (539, skipped=2)
python -m unittest tests.test_schema_v2_validation tests.test_schema_v2_json_schema tests.test_t12_prediction_schema → OK (32)
python -m unittest tests.test_governance_*                 → OK (31)
import ambiguity_manager.model                             → False False False
```

## Unresolved questions for D1B

1. Pinned-runtime inspection method for Qwen3 response-mode / thinking disablement.
2. vLLM structured-decoding parameter names from pinned container docs.
3. Whether regeneration prompts should include prior attempt diagnostics or schema-error summaries only.
4. Prediction-specific provenance enum/policy resolution before official experiments.
5. Chat-template ownership boundary once response mode is verified.

## Explicit non-claims

D1A does **not** claim:

- Qwen3 thinking mode is disabled;
- chat-template rendering is verified;
- vLLM guided decoding is verified;
- the model declares metric eligibility;
- custom route-condition metadata alone enforces output shape;
- a custom `context` chat role is supported;
- Stage D is complete;
- Stage E is ready.
