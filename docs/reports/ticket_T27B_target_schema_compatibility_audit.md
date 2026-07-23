# T27B — Target / Schema Compatibility Audit

**Status:** Architecture and assets prepared; **T27B live training/eval has not been run.**  
**Ticket:** T27B — Production-Schema Structured-Emission Recovery  
**Envelope:** `full_schema_envelope_v1`  
**Date frozen (thresholds/policy):** 2026-07-23

## Defect map (T27 job 6059)

| Aspect | Observation |
| --- | --- |
| Training target | Partial `training_semantic_target_v1` (~6.79% supervised tokens) |
| Inference contract | Full 25-field production schema `t12_model_semantic_output` |
| Result | 0/4 accepted on sealed validation |
| Adapter behaviour | Often echoed JSON Schema meta-keys (`properties` / `required` / `type`) |

Root cause: train/infer schema mismatch. The model learned a sparse partial object, then was asked to emit the full production envelope.

**Retained evidence (read-only):** run `t12-qlora-task-aligned-20260723T074715Z-991732e`, job **6059**  
(`configs/model/evidence/t27_task_aligned_qlora_smoke.json`, `docs/reports/ticket_T27_task_aligned_qlora_smoke.md`).

## Job-6059 failure classification (8 outputs)

| Record | Role | Status | Earliest stage |
| --- | --- | --- | --- |
| clara:1003 | base | schema_invalid | unknown_field (invented nested scene/action schema) |
| clara:1003 | adapter | schema_invalid | unknown_field (name/type/description descriptors) |
| clara:1180 | base | no_json | no_json |
| clara:1180 | adapter | schema_invalid | unknown_field (properties/required/type) |
| clara:1349 | base | no_json | no_json |
| clara:1349 | adapter | schema_invalid | unknown_field |
| codraw_icr_v2:4784 | base | schema_invalid | unknown_field (JSON Schema wrapper) |
| codraw_icr_v2:4784 | adapter | schema_invalid | unknown_field |

These four validation IDs remain **forbidden** for T27B tuning and selection.

## Field matrix summary (25 model-owned fields)

Machine-readable audit: `configs/model/t27b_production_schema_coverage_v1.json`.

| Treatment class | Fields |
| --- | --- |
| Always masked unavailable envelope | `unresolved_slots`, `supporting_evidence`, `resolved_slots`, `resolution_method`, `resolution_evidence`, `context_sampling_uncertainty` |
| Strong when eligible / weak when weakly eligible | speech/intent, CPC, candidates, ambiguity, compound, risk_relevant, route, clarification, rejection |
| Honest-unknown permitted (use null as masked filler) | `risk_level`, `capability_status` |

All 25 fields remain **required at inference**. Unavailable values appear only as schema-shaped envelope fillers with **masked** value tokens — never as fabricated supervised negatives.

## Chosen architecture: `full_schema_envelope_v1`

Every training target uses the **same complete production-compatible structural envelope**:

1. Structural tokens (braces, brackets, commas, colons, quotes, field names, stable nested keys) are **supervised**.
2. Strong/weak semantic values retain token IDs per eligibility (weak metadata recorded; causal-LM token weight documented as 1.0).
3. Unavailable semantic **value** tokens are masked to `-100`.
4. CPC always present as a full 13-slot object; when unavailable, `status=unknown` / `value=null` with values masked and structure supervised.
5. Lists never supervised use `[]` as structural placeholders with masked value tokens.
6. Booleans never known use `false` in the envelope with the value token masked (do not supervise `false` as a negative).
7. Nullable strings use `null` with the null token masked.

Unsafe route overlays (e.g. supervised `clarify` without clarification fields) are rejected at envelope build so dataset construction can skip them.

## Policies (frozen before live results)

Policy file: `configs/model/full_schema_envelope_policy_v1.json`.

**Minimum useful supervision (frozen):**

- `min_semantic_supervised_tokens_per_example`: 1
- `min_structural_supervised_tokens_per_example`: 1
- `min_mean_supervised_token_percentage`: 12.0 (materially above ~6.79% without fabricating labels)

**Pass thresholds (frozen):**

- sealed final count 8; base/adapter attempted ≥ 8
- adapter parse ≥ 6; schema ≥ 5; semantic ≥ 1; safety ≥ 1; final accepted ≥ 1
- adapter differs from base ≥ 1
- unsupported commitment accepted max 0

## What T27B builds next (this ticket slice)

| Asset | Role |
| --- | --- |
| `full_schema_envelope.py` | Envelope builder + segments |
| `full_schema_token_masking.py` | Segment-aware loss masks |
| `t27b_prompt_contract.py` | Full-schema prompt (no JSON Schema document echo) |
| `t27b_structured_validation.py` | Multi-stage failure classification |
| `t27b_datasets.py` | Diagnostic (12), sealed final (8), training (128) |

**Not started:** full training orchestrator / T28.

## Explicit non-goals / constraints

- Do not modify job-6059 evidence artefacts.
- Do not change `selected_identities` (adapter/strategy remain null).
- Do not change the production semantic schema.
- Do not use `source_holdout`, T13 calibration, future manual, or supervisor annotations.
- Do not tune against the four historical validation IDs above.
