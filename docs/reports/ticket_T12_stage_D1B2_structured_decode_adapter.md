# T12 Stage D1B2 — Pinned vLLM Structured-Output Adapter

**Stage:** D1B2 (adapter only; no engine start, no chat-template rendering)
**Branch:** `feature/t12-cluster-redesign`
**Starting SHA:** `faddb43d3234a094a9adbd5b58c4b9fd3b309a85`
**Date:** 2026-07-11
**Governance:** DEV-20260711-001 (synthetic-only preparatory work; T11 remains BLOCKED)

## Scope

Stage D1B2 delivers CPU-only:

- pinned vLLM 0.20.1 structured-output adapter;
- semantic-schema identity verification before parameter construction;
- lazy dependency loading with injectable classes for tests;
- integration with `VllmBatchBackend._build_sampling_params()` when Stage-D structured-output configuration is explicitly enabled;
- frozen structured-decode contract;
- mocked CPU tests.

## Non-scope

- vLLM engine start or model/tokenizer load;
- Qwen3 chat-template rendering or `enable_thinking` selection;
- response-mode verification (`ResponseModeStatus` remains unverified);
- engine-time schema compilation verification (deferred to D2);
- Stage D1C, D2, or Stage E;
- SSH, Slurm, or Apptainer execution;
- lossy schema adaptation or unconstrained generation fallback.

## Initial failing tests (red phase)

Before implementation:

```text
python -m unittest tests.test_t12_structured_decode -v
ModuleNotFoundError: No module named 'ambiguity_manager.model.structured_decode'
```

Representative backend integration tests were added after adapter skeleton; Stage-C regression tests remained green throughout green phase.

## Exact pinned API implemented

From D1B1 measured runtime (`configs/model/evidence/t12_stage_d1b1_pinned_runtime.json`):

| Item | Value |
|---|---|
| vLLM version | `0.20.1` |
| `SamplingParams` | `vllm.sampling_params.SamplingParams` |
| Structured-output field | `structured_outputs` |
| Structured-output class | `vllm.sampling_params.StructuredOutputsParams` |
| Schema parameter | `json` (dict) |
| Construction shape | `StructuredOutputsParams(json=<semantic schema dict>)` then `SamplingParams(..., n=1, structured_outputs=<instance>)` |

Not implemented: `guided_decoding`, `GuidedDecodingParams`, `json_schema=`, compatibility fallback, lossy schema transformation, unconstrained fallback.

## Frozen structured-decode contract

**Path:** `configs/model/t12_structured_decode_contract.json`
**Contract hash (canonical JSON SHA-256):** `0c0aae4cff8e80c87a57833d476d7b41310a49c3256cf48b71593aca544bc5b9`

| Field | Value |
|---|---|
| Contract version | `1.0.0` |
| Required vLLM version | `0.20.1` |
| Semantic schema relpath | `configs/model/schema/t12_model_semantic_output.schema.json` |
| Semantic schema SHA-256 | `232235fec53ee38eafcd714fd53664b250e848a6b0f75fca1ff7ec903b08cfb4` |
| Derivation version | `t12-d1a-1.1.0` |
| Completions per request | `1` |
| Lossy adaptation | `false` |
| Unconstrained fallback | `false` |
| Guided decoding | `false` |
| D1B1 evidence | `configs/model/evidence/t12_stage_d1b1_pinned_runtime.json` |
| Response-mode status | `unverified_until_pinned_runtime_inspection` |
| Engine-time compilation | `unverified_until_stage_d2` |
| Live output verification | `pending_stage_d2_live_schema_smoke` |

## Schema identity verification

Before parameter construction the adapter:

1. loads the committed semantic schema from the contract path;
2. canonicalises deterministically (`canonical_json_bytes`);
3. computes SHA-256 and requires `232235fec53ee38eafcd714fd53664b250e848a6b0f75fca1ff7ec903b08cfb4`;
4. requires derivation version `t12-d1a-1.1.0`;
5. meta-validates with `jsonschema` Draft 2020-12;
6. rejects mutation or mismatch with `SchemaIdentityMismatchError`.

No conditionals, required fields, `additionalProperties: false`, or enums are removed or rewritten.

## Lazy import behaviour

- No top-level import of `vllm`, `torch`, or `transformers`.
- vLLM is imported via `importlib.import_module("vllm")` only when both API classes are unresolved (no injection and no resolver).
- Injected classes and resolvers support CPU tests without vLLM installed.
- Importing `ambiguity_manager.model` does not load ML libraries.

## Adapter construction

**Module:** `src/ambiguity_manager/model/structured_decode.py`
**API:** `build_structured_sampling_params(generation_config, structured_decode_contract, *, sampling_params_class=None, structured_outputs_class=None, detected_vllm_version=None, ...)`

Behaviour:

- supplies schema as a Python `dict` to `StructuredOutputsParams(json=schema_dict)`;
- builds `SamplingParams(temperature=..., top_p=..., max_tokens=..., n=1, structured_outputs=...)`;
- does not mutate caller `generation_config`;
- returns `StructuredDecodeBuildResult` with deterministic metadata (`contract_hash`, `schema_hash`, API identity, `construction_status=constructed`).

## Backend integration

**Modified:** `src/ambiguity_manager/model/backends/vllm_batch.py`

- Optional `structured_decode` block on runtime configuration.
- Stage-C configs without `structured_decode.enabled` retain prior unstructured `SamplingParams` behaviour.
- When `structured_decode.enabled` is true, `_build_sampling_params()` invokes the adapter (unless an injected `sampling_params_factory` is supplied).
- Adapter failure raises `VllmBatchBackendError` before `engine.generate()` — no unconstrained fallback.
- Structured-output construction occurs once per `generate_batch()` invocation (shared across internal chunks).
- `n=1` enforced via contract `completions_per_request`.
- Last construction metadata exposed via `last_structured_decode_metadata`.

**Stage-D runtime config:** `configs/cluster/t12_stage_d_vllm_runtime.json` (does not alter historical C2B runtime config `configs/cluster/t12_vllm_batch_runtime.json`).

## Failure taxonomy

| Error class | Meaning |
|---|---|
| `VllmUnavailableError` | vLLM not importable for real construction |
| `WrongVllmVersionError` | detected version ≠ `0.20.1` |
| `MissingApiClassError` | `SamplingParams` or `StructuredOutputsParams` absent |
| `MissingApiFieldError` | required `structured_outputs` or `json` constructor field absent |
| `SchemaIdentityMismatchError` | schema hash or derivation version mismatch |
| `SchemaInvalidError` | Draft 2020-12 meta-validation failure |
| `ParameterConstructionError` | pinned construction raised an exception |

Backend maps these to prefixed `VllmBatchBackendError` messages (`structured_decode_*`).

## No-lossy-adaptation policy

Contract forbids `lossy_schema_adaptation_permitted`. Adapter passes the verified semantic schema dict unchanged to `StructuredOutputsParams(json=...)`.

## No-unconstrained-fallback policy

Contract forbids `unconstrained_fallback_permitted`. Adapter or backend construction failure propagates as an error; unstructured `SamplingParams` are not substituted.

## Response-mode separation

- `response_mode.py` **not** modified.
- Response-mode status remains `unverified_until_pinned_runtime_inspection`.
- Live output verification remains `pending_stage_d2_live_schema_smoke`.
- Structured-output adapter readiness and response-mode readiness are separate concerns.

## Engine-time compilation

Parameter-build-time construction succeeded in D1B1 inspection. Engine-time schema compilation remains **unverified** until Stage D2 live schema smoke.

## No-model / no-cluster statement

No SSH, Slurm, Apptainer, vLLM engine, model weights, or tokenizer were accessed. All validation was CPU-only local unit testing.

## Tests and exact results

```powershell
$env:PYTHONPATH = "src"
python -m unittest tests.test_t12_structured_decode -v          → OK (21)
python -m unittest tests.test_t12_vllm_batch_backend -v         → OK (32)
python -m unittest tests.test_t12_prediction_contract -v      → OK (54)
python -m unittest tests.test_t12_response_mode -v            → OK (7)
python -m unittest tests.test_t12_stage_d1b1_runtime_evidence -v → OK (22)
python -m unittest discover -s tests -p "test_t12_*.py"         → OK (588)
python -m unittest tests.test_governance_*                      → OK (31)
python -c "import sys; import ambiguity_manager.model; print('torch' in sys.modules, 'transformers' in sys.modules, 'vllm' in sys.modules)"
# False False False
```

## Remaining requirements for D2

1. Live engine-time schema compilation inside pinned SIF.
2. Live structured-output smoke with real `SamplingParams` / `StructuredOutputsParams` classes.
3. Response-mode / thinking-control verification separate from adapter readiness.
4. Bounded regeneration and repair loop wiring (D1C+).
5. Schema-valid output verification on synthetic fixtures.

## Explicit non-claims

D1B2 does **not** claim:

- engine-time schema compilation passed;
- response mode is verified;
- Qwen thinking is disabled;
- live output is schema-valid;
- Stage D is complete;
- Stage E is ready.
