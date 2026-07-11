# T12 Slice 3A — Model candidate and licence verification

**Ticket:** T12  
**Slice:** 3A (corrected)  
**Date:** 2026-07-11  
**Verifier:** AUTHOR-01  
**Status:** PASS

## Scope

Slice 3A performed authoritative, ungated model-candidate discovery and licence verification only. No model weights were downloaded, no `from_pretrained` was invoked, no inference was run, and `selected_model` remains `null`.

## Candidate reconciliation

| Count | Value |
|-------|-------|
| Evaluated | 9 |
| Eligible (`candidate_evaluated`) | 5 |
| Rejected | 4 |
| Selected | 0 |
| `selected_model` | `null` |

## Rejected candidates

| Entry ID | Model | Reason |
|----------|-------|--------|
| t12-cand-003 | TinyLlama/TinyLlama-1.1B-Chat-v1.0 | Official context limit 2048 < mandatory T12 target 4096 |
| t12-rej-001 | google/gemma-2-2b-it | Gated (`gated_access=manual`) |
| t12-rej-002 | meta-llama/Llama-3.2-1B-Instruct | Gated (`gated_access=manual`) |
| t12-rej-003 | TheBloke/Qwen2.5-1.5B-Instruct-GPTQ | Third-party quantised repository; not authoritative provider checkpoint |

## Eligible candidates

| Entry ID | Model | Revision SHA |
|----------|-------|--------------|
| t12-cand-001 | Qwen/Qwen2.5-1.5B-Instruct | `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` |
| t12-cand-002 | HuggingFaceTB/SmolLM2-1.7B-Instruct | `31b70e2e869a7173562077fd711b654946d38674` |
| t12-cand-004 | microsoft/Phi-3.5-mini-instruct | `2fe192450127e6a83f7441aef6e3ca586c338b77` |
| t12-cand-005 | stabilityai/stablelm-2-zephyr-1_6b | `2f275b1127d59fc31e4f7c7426d528768ada9ea4` |
| t12-cand-006 | Qwen/Qwen2.5-3B-Instruct | `aa8e72537993ba99e69dfaafa59ed015b17504d1` |

## Recommendations

| Role | Entry ID | Model |
|------|----------|-------|
| First probe | t12-cand-001 | Qwen/Qwen2.5-1.5B-Instruct |
| Fallback | t12-cand-002 | HuggingFaceTB/SmolLM2-1.7B-Instruct |

## Frozen download cap (authoritative bytes)

| Field | Value |
|-------|-------|
| `maximum_cumulative_download_bytes` | 32212254720 |
| Display metadata | 30 GiB |
| Primary `estimated_download_bytes` | 3098955668 |
| `remaining_headroom_bytes` | 29113299052 |

Arithmetic: `3098955668 + 29113299052 = 32212254720`

Enforcement uses bytes only. Decimal 30 GB (30000000000) is not used.

## Deterministic download allowlist (Slice 3B plan)

**Include patterns:** `*.safetensors`, `config.json`, `generation_config.json`, `tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`, `vocab.json`, `merges.txt`, `*.model`, `LICENSE*`, `README.md`, `model.safetensors.index.json`

**Exclude patterns:** `pytorch_model*.bin`, `tf_model*.h5`, `flax_model*.msgpack`, `onnx/**`, `*.onnx`, `*.gguf`, `*.ggml`, `*-gptq*`, `*-awq*`, `original/**`

Pinned revision: `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` on official `Qwen/Qwen2.5-1.5B-Instruct` only.

Preflight: verify 50 GiB free disk, recheck cumulative cache, assert ungated, fail if download exceeds estimate + 104857600 byte tolerance. Stop before checkpoint load.

## Confirmations

- No model was downloaded or executed.
- `checkpoint_load_verified` remains `false`.
- `selected_model` remains `null`.
- T11 remains **BLOCKED**.
- T13/T14 were not started.
- Slice 3B was not started.

## Slice 3A verdict

**PASS**
