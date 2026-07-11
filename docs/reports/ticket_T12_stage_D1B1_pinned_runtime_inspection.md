# T12 Stage D1B1 — Pinned Qwen3 and vLLM Structured-Output Runtime Inspection

**Stage:** D1B1 (runtime inspection only; no adapter implementation)
**Branch:** `feature/t12-cluster-redesign`
**Starting SHA:** `885ae878120a2fd5db3950056ea39f4a4f847704`
**Date:** 2026-07-11
**Governance:** DEV-20260711-001 (synthetic-only preparatory work; T11 remains BLOCKED)

## Scope

Stage D1B1 delivers read-only pinned-runtime inspection of:

- vLLM 0.20.1 structured-output API (`SamplingParams`, `StructuredOutputsParams`);
- D1A semantic JSON schema supply to the pinned runtime without modification;
- Qwen3-8B tokenizer/chat-template thinking-control behaviour;
- sanitised machine-readable evidence and CPU-only evidence tests.

## Non-scope

- vLLM backend modification;
- structured-decoding adapter implementation (Stage D1B);
- model weight load or generation;
- Stage D1C, D2, or Stage E;
- live reasoning-leakage verification.

## SSH and source transfer

SSH alias `wits-mscluster` authenticated in BatchMode without storing credentials.

| Field | Value |
|---|---|
| Transfer method | `git_archive` at commit `885ae878120a2fd5db3950056ea39f4a4f847704` |
| Archive SHA-256 | `16faf0e99eba96ea441b39c56f2be54272bab44eed39fb8338194c7c8e51f8d2` |
| Extraction path template | `${T12_CLUSTER_ROOT}/runs/stage-d1b1/stage-d1b1-20260711T202100Z-885ae87/source/t12-src` |
| Working tree transferred | false |

## Run identity

| Field | Value |
|---|---|
| Run ID | `stage-d1b1-20260711T202100Z-885ae87` |
| Remote path template | `${T12_CLUSTER_ROOT}/runs/stage-d1b1/stage-d1b1-20260711T202100Z-885ae87` |
| Slurm partition | `biggpu` (exclusive) |
| Slurm job ID (measurement only) | `1849` |
| Allocated node (measurement only) | `mscluster110` |
| Operator nodelist pin (measurement only) | `mscluster110` (Blackwell; legacy probe on `mscluster106` superseded) |

## Container verification

| Field | Value |
|---|---|
| Container | `vllm-openai-v0.20.1.sif` |
| Path template | `${T12_CONTAINER_SIF}` |
| Expected SHA-256 | `d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1` |
| Observed SHA-256 | `d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1` |
| Hash method | full SHA-256 |
| Elapsed (Blackwell run) | 3.079 s |
| Elapsed (cold read reference) | 81.408 s |
| Size | 7 657 443 328 bytes |

## Runtime versions

| Package | Version |
|---|---|
| Python | 3.12.13 |
| vLLM | 0.20.1 |
| Transformers | 5.7.0 |

## GPU observation

| Field | Value |
|---|---|
| GPU | NVIDIA RTX PRO 6000 Blackwell Workstation Edition |
| CUDA available | true |
| GPU memory allocated | 0 bytes |
| GPU memory reserved | 0 bytes |

## vLLM structured-output API (measured)

| Item | Measured value |
|---|---|
| `SamplingParams` module | `vllm.sampling_params.SamplingParams` |
| Structured-output field on `SamplingParams` | `structured_outputs` |
| `guided_decoding` field | absent |
| `GuidedDecodingParams` import | not available (ImportError) |
| Structured-output class | `StructuredOutputsParams` |
| Structured-output module | `vllm.sampling_params.StructuredOutputsParams` |
| JSON schema parameter name | `json` |
| Accepted type (verified) | `dict` (also typed `str \| dict \| None`) |
| Rejected parameter name | `json_schema` (ValidationError) |

Verified construction (no engine load):

```python
StructuredOutputsParams(json=<D1A semantic schema dict>)
SamplingParams(
    temperature=0.0,
    max_tokens=16,
    n=1,
    structured_outputs=<StructuredOutputsParams instance>,
)
```

**Construction classification:** `supported_as_is`

No lossy schema adaptation was required. The committed D1A semantic schema (Draft 2020-12, conditionals, `additionalProperties: false`, full required-field set) constructed successfully at parameter-build time.

## Semantic schema

| Field | Value |
|---|---|
| Derivation version | `t12-d1a-1.1.0` |
| Canonical export SHA-256 | `232235fec53ee38eafcd714fd53664b250e848a6b0f75fca1ff7ec903b08cfb4` |
| Draft 2020-12 meta-validation | pass |

## Tokenizer and chat-template inspection

Pinned snapshot: `Qwen/Qwen3-8B` @ `b968826d9c46dd6066d109eabc6255188de91218`

| Artefact | SHA-256 |
|---|---|
| `tokenizer_config.json` | `d5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101` |
| `tokenizer.json` | `aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4` |
| `vocab.json` | `ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910` |
| `merges.txt` | `8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5` |

| Field | Value |
|---|---|
| Tokenizer class | `Qwen2Tokenizer` |
| Loading method | `AutoTokenizer.from_pretrained(local_files_only=True)` |
| Chat template SHA-256 | `a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8` |
| Thinking-control variable | `enable_thinking` (referenced in template Jinja) |
| Non-thinking probe method | `apply_chat_template(..., enable_thinking=False)` |
| Default rendered prompt SHA-256 | `2a14310d1afbe366e55474178286348d5de3a75fd5004824e8129e0f4ccb06e8` |
| Non-thinking rendered prompt SHA-256 | `d1f350dd89bf84f269653c1c572f0c67c7477134dfeb5346204f645be35bdc4e` |
| Renderings differ | true |
| Default contains think markers | false |
| `enable_thinking=False` injects empty think block | true |
| Generation prompt included | true |
| Output cleaning likely required later | true |

**Template-control classification:** `template_inspection_inconclusive`

Observed behaviour: default template rendering (no `enable_thinking` argument) omits thinking markers and ends with `<|im_start|>assistant\n`. Explicit `enable_thinking=False` injects an empty `<think>\n\n</think>\n\n` block before generation. This does not yet prove non-thinking live output and does not satisfy verified non-thinking control.

**Generation-output verification:** `pending_stage_d2_live_schema_smoke`

## No model-weight load proof

| Check | Result |
|---|---|
| `vllm.LLM` instantiated | false |
| Generation called | false |
| `.safetensors` shards opened | 0 |
| GPU memory allocated | 0 bytes |
| Offline flags | `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` |
| Network fallback | false |

## Remote evidence retained

Under `${T12_CLUSTER_ROOT}/runs/stage-d1b1/stage-d1b1-20260711T202100Z-885ae87`:

- inspection script;
- source archive extraction;
- full SIF hash output;
- `d1b1_inspection_evidence.json`;
- Slurm job log.

Superseded legacy-GPU probe retained at `${T12_CLUSTER_ROOT}/runs/stage-d1b1/stage-d1b1-20260711T201450Z-885ae87`.

## Governance invariants

- T11 remains **BLOCKED**
- `selected_model` remains `null`
- No protected or research-pool data used
- Stage D1B adapter **not** implemented
- `response_mode.py` **not** modified

## Explicit non-claims

D1B1 does **not** claim:

- structured-decoding adapter is implemented;
- live model output omits reasoning leakage;
- Qwen3 thinking mode is disabled in production;
- Stage D1B, D1C, D2, or Stage E are ready;
- T11 is unblocked.

## Unresolved questions for D1B

1. Whether default template rendering (without `enable_thinking`) is the correct D1B non-thinking prompt path.
2. Whether live output requires stripping of empty or populated thinking blocks despite template choice.
3. Whether vLLM schema compilation succeeds at engine start with the full D1A conditionals (parameter construction passed; engine compile deferred to D1B/D2).
