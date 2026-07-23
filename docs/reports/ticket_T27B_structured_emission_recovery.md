# T27B — Production-Schema Structured-Emission Recovery

**Status: BLOCKED** (structured-emission gate)

Author: Mohammed Bangie — 2610990  
Ticket: T27B  
Live run: `t12-qlora-emission-recovery-20260723T090929Z-3ae20c7` / Slurm **6382** / `mscluster111`

## Verdict

Mechanics, data isolation, and supervision-density gates **PASS**.  
Structured-emission gate **BLOCKED**: adapter **0/8** final accepted (1 parse-valid, 0 schema-valid).  
Frozen thresholds were not met. Do **not** begin T28. Do **not** select an adapter.

Job-6059 evidence remains retained and was not overwritten:
`t12-qlora-task-aligned-20260723T074715Z-991732e` / job **6059**.

## What passed

| Gate | Result |
|------|--------|
| Real cluster 4-bit QLoRA | PASS |
| Base frozen / adapter trainable | PASS (frozen 4,717,851,648 / trainable 7,667,712) |
| `full_schema_envelope_v1` targets | PASS |
| Real token masks + structural/semantic supervision | PASS (mean supervised **34.01%**, prior job 6059 ≈ **6.79%**) |
| Full checkpoint + full resume | PASS |
| Adapter save/reload separate from base | PASS |
| 128 / 12 / 8 isolation + leakage | PASS |
| Operator verify | `VERIFY_PASSED` |

## What failed

Frozen thresholds (set before live run):

| Metric | Threshold | Observed |
|--------|-----------|----------|
| adapter parse-valid | ≥ 6/8 | **1** |
| adapter schema-valid | ≥ 5/8 | **0** |
| adapter semantic/safety/final accepted | ≥ 1 | **0** |
| adapter≠base | ≥ 1 | **8** (met) |

Adapter failure stages on the sealed eight: truncation (3), no_json (2), json_parse_failed (2), unknown_field (1).  
Base: no_json (5), truncation (3).  
Transport: `hf_generate_unconstrained` (never counted as acceptance).

## Architecture used

- Envelope: `full_schema_envelope_v1`
- Prompt: `t27b_full_schema_prompt_v1` (field-name contract; no embedded JSON Schema document)
- Structural tokens supervised; unavailable semantic values masked (−100)
- One controlled recovery attempt only

## Prior technical failures (preserved)

1. Job **6307** (`ba31f28`): missing `jsonschema`
2. Job **6350** (`6fd6dcf`): install without dependency closure

Job **6382** completed real training after the runtime fix.

## Decision

`T27B status = BLOCKED`  
`T27 ticket_status = BLOCKED`  
`selected_adapter = null`  
`selected_model_strategy = null`  
`valid_for_official_use = false`  
`t28_may_begin = false`

**Do not repeat another minor full-envelope training tweak.**  
Next architecture decision should evaluate:

**task-conditioned partial-schema prediction + deterministic StructuredAnalysis assembly**

## Compact evidence

- `configs/model/evidence/t27b_structured_emission_recovery.json`
- `tests/test_t27b_structured_emission_recovery_evidence.py`
