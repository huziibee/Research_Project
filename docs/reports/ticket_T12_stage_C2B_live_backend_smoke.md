# T12 Stage C2B — Live persistent vLLM backend smoke (committed correlation fix)

**Ticket:** T12  
**Stage:** C2B (controlled live cluster backend smoke, resume, conflict)  
**Measurement timestamp:** 2026-07-11T19:27:33Z  
**Authority:** DEV-20260711-001  
**Status:** Stage C2B ready for review — Stage C **not** complete

## 1. Scope

Stage C2B proves on live Wits `biggpu` hardware that the committed `VllmBatchBackend` from the output-correlation fix commit executes unchanged inside the pinned vLLM SIF:

- compute-node full SIF SHA-256 matches the immutable expected hash;
- runtime preflight passes with offline snapshot resolution;
- one persistent direct-Python vLLM engine serves multiple generation batches;
- four deterministic synthetic requests are fully accounted for under `batch_size=2`;
- atomic shard output and completion manifest validate;
- exact completed-shard resume skips without engine startup;
- completed backend-config conflict blocks without mutating evidence.

## 2. Historical preliminary run (not accepted)

Earlier run `stage-c2b-20260711T181903Z-ab00ef5` found that vLLM 0.20.1 returned numeric/internal `request_id` values that the pre-fix C2A normaliser rejected as `unknown_output_id` for `batch_size > 1`. A cluster-side instrumented/workaround driver proved the intended positional correction, but that workaround was **not** accepted as C2B evidence.

This rerun used committed source from `b7dfba94ceae2f430e9eec7a64c4c6cd24b5a7a2` unchanged. No cluster-side workaround, instrumented driver, monkey-patch, or backend replacement was used. Preliminary backend-run hashes are **not** reused.

## 3. Non-scope (explicit)

Stage C2B does **not**:

- implement or evaluate schema-v2 prompting (Stage D);
- enforce structured JSON decoding or repair;
- disable Qwen3 thinking mode;
- access research-pool or protected data;
- train or attach an adapter;
- claim Stage C, Stage D, or T12 complete.

## 4. Governance boundary

- T11 remains **BLOCKED**.
- DEV-20260711-001 authorises synthetic-only preparatory work.
- `model_licence_register.selected_model` remains `null`.
- Model candidate status remains `provisionally_selected_for_cluster_validation`.

## 5. Local repository state at start

- Branch: `feature/t12-cluster-redesign`
- HEAD: `b7dfba94ceae2f430e9eec7a64c4c6cd24b5a7a2`
- Subject: `fix(t12): correlate vLLM batch outputs by documented prompt order`
- Remote HEAD matched local.
- No tracked or staged changes before C2B evidence replacement.

## 6. SSH BatchMode

SSH alias `wits-mscluster` authenticated in BatchMode without storing credentials or private-key paths in repository artefacts.

## 7. Source transfer

| Field | Value |
|-------|-------|
| Method | `git_archive` of commit `b7dfba94ceae2f430e9eec7a64c4c6cd24b5a7a2` |
| Archive SHA-256 | `ff0e99718443075167c0d995ff4d518c3151838fba11f645d123bc228f2d96b4` |
| Backend file SHA-256 | `816e9996eab58cea3075558517dde47698ea9ef0ec553704c2f79c782a61dc29` |
| Extraction path template | `${T12_CLUSTER_ROOT}/runs/stage-c2b/stage-c2b-rerun-20260711T192157Z-b7dfba9/source/t12-src` |
| Execution method | `committed_backend_unchanged` |
| Cluster-side workaround | false |

Dirty local working tree was not transferred. Executed backend blob hashes match the fix commit archive.

## 8. Run identity

| Field | Value |
|-------|-------|
| Run ID | `stage-c2b-rerun-20260711T192157Z-b7dfba9` |
| Remote path template | `${T12_CLUSTER_ROOT}/runs/stage-c2b/stage-c2b-rerun-20260711T192157Z-b7dfba9` |
| Shard | `shard-000` |
| Slurm job | `1844` (measurement only) |
| Allocated node | `mscluster110` (measurement only; temporary `--nodelist` for bounded smoke) |

## 9. Container integrity

| Field | Value |
|-------|-------|
| Method | `full_sha256` on allocated compute node |
| Expected | `d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1` |
| Observed | `d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1` |
| Elapsed (s) | 13.597 |
| Match | true |

## 10. Preflight

Preflight status: **pass**

Observed on allocated node:

- GPU: NVIDIA RTX PRO 6000 Blackwell Workstation Edition
- VRAM (MiB): 97887
- Compute capability: 12.0
- Driver: 595.71.05
- CUDA available: true
- Exclusive allocation: true
- Snapshot inventory: 15 files, 16397461266 bytes, 5 safetensors shards
- Offline resolution: passed
- Network fallback: false
- Effective HF_HOME template: `${T12_HF_CACHE}`
- Effective Hub cache template: `${T12_HF_CACHE}/hub`

## 11. Synthetic input

Four deterministic records:

| ID | Ordinal | Prompt class |
|----|---------|--------------|
| `c2b-smoke-0001` | 0 | brief response |
| `c2b-smoke-0002` | 1 | arithmetic text |
| `c2b-smoke-0003` | 2 | categorisation |
| `c2b-smoke-0004` | 3 | paraphrase |

Input SHA-256: `3a0b771d759bcdf7070f6c4099efaa6aa561e5a6614d9ac3c78ed284f4643e8a`

## 12. Runtime configuration (C2B smoke only)

| Parameter | Value |
|-----------|-------|
| Backend | `vllm_batch_direct` |
| Mode | direct Python vLLM inside SIF |
| Batch size | 2 |
| Max tokens | 64 |
| Temperature | 0.0 |
| Tensor parallel size | 1 |
| GPU memory utilisation | 0.5 |
| Offline flags | `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` |
| Verification label | `c2b_smoke_configuration` |

## 13. First-run results (committed CLI)

| Metric | Value |
|--------|-------|
| Driver | `scripts/t12_cluster_run_batch.py` (committed) |
| Engine start count | 1 |
| Generation batch-call count | 2 |
| Requests accounted | 4 |
| Success | 4 |
| Failure | 0 |
| `unknown_output_id` count | 0 |
| `engine_output_order_mismatch` count | 0 |
| Canonical result IDs | equal to the four caller IDs |
| Engine request IDs | diagnostic only; not promoted to canonical project IDs |
| Output SHA-256 | `f8cd3cca726c6fbffc44364c155549e99a440f7d3852507abc55556574f89bf9` |
| Manifest SHA-256 | `cabec10be3da448ad9b293af382d3db2146c5f9663206f6b530947096089eafd` |

All four requests retained non-empty raw success records. Output SHA matches manifest.

## 14. Exact-resume probe

| Check | Result |
|-------|--------|
| Decision | `skip_exact_completed` |
| Engine started | false (engine start count 0) |
| Output bytes unchanged | true |
| Manifest bytes unchanged | true |
| Exit | success |

## 15. Completed-conflict probe

| Check | Result |
|-------|--------|
| Decision | `block_completed_conflict` |
| Reason | `completed_conflict:backend_config_hash` |
| Engine started | false (engine start count 0) |
| Isolated copy used | true |
| Output bytes unchanged | true |
| Manifest bytes unchanged | true |
| Exit | non-zero |

Canonical successful bytes were not mutated.

## 16. Remote retention

Retained under `${T12_CLUSTER_ROOT}/runs/stage-c2b/stage-c2b-rerun-20260711T192157Z-b7dfba9`:

- source archive and extracted tree;
- synthetic input;
- runtime facts and preflight result;
- full-hash evidence;
- shard raw/parsed outputs and completion manifest;
- job log;
- resume and conflict probe outcomes.

Also retained (historical only): `${T12_CLUSTER_ROOT}/runs/stage-c2b/stage-c2b-20260711T181903Z-ab00ef5`.

Not deleted: SIF, model snapshot, shared cache, other run directories.

## 17. Explicit non-claims

This report does **not** claim:

- schema-v2 validity or semantic correctness;
- Stage D or Stage E completion;
- benchmark throughput;
- final model selection;
- T11 ethics clearance.

## Cross-references

- `configs/model/evidence/t12_cluster_c2b_backend_smoke.json`
- `configs/model/evidence/t12_cluster_live_verification.json`
- `docs/reports/ticket_T12_stage_C2A_vllm_backend.md`
- `docs/decisions/ADR_T12_cluster_inference_architecture.md`
