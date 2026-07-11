# T12 Stage B2/B2R — Live cluster verification report

**Ticket:** T12  
**Stages measured:** B2 (initial live verification), B2R (corrective offline-resolution verification)  
**Ingestion stage:** B3 (sanitised repository evidence)  
**Measurement date:** 2026-07-11 (time not recorded consistently; date-only precision)  
**Authority:** DEV-20260711-001  
**Status:** Live read-only verification complete; sanitised evidence ingested in B3

## 1. Purpose

Record sanitised evidence from live, read-only Wits cluster verification of the T12 inference stack: shared storage, Apptainer container identity, container software versions, Qwen3-8B snapshot inventory, corrected Hugging Face Hub cache semantics, Slurm scheduler observations, and a minimal GPU tensor probe. No model weights were loaded. No vLLM engine was started.

## 2. Governance boundary

- T11 remains **BLOCKED** on the pending institutional ethics determination.
- DEV-20260711-001 authorises this preparatory T12 work only.
- No protected data was accessed.
- No research-pool records were used.
- No annotation collection, T13, or T14 work was started.
- `selected_model` in the licence register remains `null`.
- Model candidate status remains `provisionally_selected_for_cluster_validation`.
- Full raw terminal transcripts were **not** committed to the repository.

## 3. Local repository state

Stage B3 ingests measured facts into sanitised JSON evidence under `configs/model/evidence/` and updates active cluster manifests. Personal absolute paths, cluster usernames, and credentials are excluded. Path templates use `${T12_CLUSTER_ROOT}`, `${T12_HF_CACHE}`, and `${T12_CONTAINER_SIF}`.

## 4. SSH BatchMode result

SSH connectivity was verified in BatchMode (non-interactive) without storing credentials, passwords, private-key paths, or personal usernames in repository artefacts. No remote files were modified during B2/B2R.

## 5. Storage summary

| Property | Value |
|----------|-------|
| Root template | `${T12_CLUSTER_ROOT}` |
| Ownership scope | current cluster user |
| Permissions | `drwx------` |
| Readable / writable | true / true |
| Filesystem | NFS-backed `/home-mscluster` storage |
| Total bytes | 80,007,730,823,168 |
| Available bytes | 61,766,580,043,776 |
| Used percent | 23 |

Subdirectory sizes (bytes): containers 7,657,443,461; hf-cache 16,404,839,440; logs 25,320; models 1,916; scripts 13,122; apptainer-cache 0.

## 6. Container identity

| Field | Value |
|-------|-------|
| Filename | `vllm-openai-v0.20.1.sif` |
| Path template | `${T12_CONTAINER_SIF}` |
| Expected immutable SHA-256 | `d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1` |
| Observed sidecar SHA-256 | `d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1` |
| Exact size (bytes) | 7,657,443,328 |
| Sidecar SHA match | true |
| Sidecar timestamp | 2026-07-11T14:59:19Z |
| Container execution verified | true |
| Container package identity verified | true |
| Identity status | `size_and_sidecar_match` |

Apptainer version observed: **1.4.5**.

## 7. Container software versions

Observed inside the SIF (no vLLM engine started):

| Package | Version |
|---------|---------|
| Python | 3.12.13 |
| PyTorch | 2.11.0+cu130 |
| PyTorch CUDA build | 13.0 |
| vLLM | 0.20.1 |
| Transformers | 5.7.0 |
| Hugging Face Hub | 1.13.0 |
| Safetensors | 0.7.0 |

## 8. Snapshot inventory

| Field | Value |
|-------|-------|
| Repository | `Qwen/Qwen3-8B` |
| Immutable revision | `b968826d9c46dd6066d109eabc6255188de91218` |
| Snapshot path template | `${T12_HF_CACHE}/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218` |
| Resolved files | 15 |
| Resolved total size (bytes) | 16,397,461,266 |
| Safetensors shards | 5 |
| Broken symlinks | 0 |

Required files observed: `config.json`, `generation_config.json`, `model.safetensors.index.json`, `tokenizer.json`, `tokenizer_config.json`, `vocab.json`, `merges.txt`.

Configuration: `model_type` = `qwen3`; architecture `Qwen3ForCausalLM`.  
Tokenizer: class `Qwen2Tokenizer` (Hugging Face naming convention); vocabulary size 151,669. This does not indicate a different model identity.

## 9. Initial offline-resolution failure (B2)

Initial offline resolution failed when `cache_dir` was set to the Hugging Face home root (`${T12_HF_CACHE}`) instead of the Hub cache subdirectory (`${T12_HF_CACHE}/hub`). The snapshot could not be resolved under the incorrect path.

## 10. Corrective B2R probes

Three corrective probes passed under required offline flags (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`):

| Probe | Method | Result |
|-------|--------|--------|
| A | Explicit `cache_dir=${T12_HF_CACHE}/hub`; exact revision pinned | PASS — snapshot path matched |
| B | `HF_HOME=${T12_HF_CACHE}`; derived Hub cache; no incorrect explicit `cache_dir`; exact revision pinned | PASS — snapshot path matched |
| C | Direct snapshot-path config and tokenizer load; weights not loaded | PASS |

Network fallback was not used.

## 11. Corrected root cause: `INCORRECT_CACHE_DIR`

Root-cause classification: **`INCORRECT_CACHE_DIR`**.

- Incorrect prior usage: `cache_dir=${T12_HF_CACHE}`
- Correct explicit Hub cache: `cache_dir=${T12_HF_CACHE}/hub`
- Also valid: `HF_HOME=${T12_HF_CACHE}` with Hub cache derived as `${T12_HF_CACHE}/hub`

## 12. Missing `refs/` was not causal

The absence of a `refs/` directory under the cache layout was **not** the cause of the initial failure. Exact pinned snapshot resolution succeeds without requiring repository logic to create or depend on `refs/`.

## 13. Scheduler observations

| Property | Value |
|----------|-------|
| Partition | `biggpu` (state UP at measurement) |
| Exclusive node required | true |
| GRES types (Slurm) | null |
| SelectType | `select/linear` |
| GPU GRES mode | not configured at measurement time |
| QoS observed | `mss_biggpu` |
| QoS evidence status | partial — no permanent job-limit claim |

Nodes mscluster106–mscluster112 observed; states at measurement were dynamic (e.g. mscluster107–109 down; 106, 110–112 idle). Verified GPU-class nodes: mscluster110, mscluster111, mscluster112 (12 CPUs, 122000 MiB memory each, `gres: null`).

Partition limits: MaxNodes 3; MaxTime 3-00:00:00; TotalCPUs 260; TotalNodes 7.

Node states and queue conditions are **dynamic** and are not encoded as permanent policy.

## 14. Live GPU tensor probe

| Property | Value |
|----------|-------|
| Probe node | mscluster110 (measurement identifier only) |
| GPU | NVIDIA RTX PRO 6000 Blackwell Workstation Edition |
| nvidia-smi VRAM (MiB) | 97,887 |
| PyTorch total VRAM (bytes) | 101,973,491,712 |
| Compute capability | 12.0 |
| Driver | 595.71.05 |
| CUDA available | true |
| Input tensor | [1.0, 2.0, 3.0] |
| Result tensor | [2.0, 4.0, 6.0] |
| Status | PASS |

No model was loaded. No vLLM engine was started. No remote output file was written.

## 15. SIF hash caveat

Fresh live SHA-256 recomputation of the SIF was **deferred** during B2 (`live_sha256_recomputed_during_b2: false`; `live_sha256_status: deferred`). Evidence records:

1. Expected immutable hash (from selection)
2. Observed sidecar hash (matches expected)
3. Exact size identity (matches expected)
4. Successful container execution and package identity
5. Deferred fresh hash recomputation

Sidecar match and size identity passed. Container execution does **not** silently substitute for a fresh content-hash PASS. A future live hash recomputation may upgrade integrity status without changing immutable selection.

## 16. No-model-load statement

No model weights were loaded during B2 or B2R. Probe C verified config and tokenizer from the pinned snapshot path only. `checkpoint_load_verified` and `inference_smoke_verified` remain `false`.

## 17. No-network-fallback statement

All acceptance offline-resolution probes used `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`. `network_fallback_used` is `false`.

## 18. No-remote-modification statement

B2/B2R were read-only verification. No remote files were modified. No Slurm jobs were submitted from this B3 ingestion task.

## 19. Remaining work

- Stage C and subsequent T12 stages (D–I) are not started.
- Fresh SIF live SHA-256 recomputation remains deferred.
- vLLM engine startup and schema-v2 inference smoke remain future stages.
- Training environment remains `planned_unverified`.
- LoRA feasibility, benchmark/recovery, and final model selection remain future gates.

## 20. Clear non-claims

This report and ingested B3 evidence do **not** claim:

- full schema-v2 inference acceptance;
- Stage E bake-off completion;
- LoRA feasibility;
- benchmark or recovery runs;
- final Qwen3-8B selection (`selected_model` remains `null`);
- T11 ethics clearance (T11 remains **BLOCKED**);
- revised T12 ticket completion.

## Cross-references

- `configs/model/immutable_selection.json`
- `configs/model/cluster_execution_policy.json`
- `configs/model/evidence/t12_cluster_live_verification.json`
- `configs/model/evidence/t12_cluster_hardware_manifest.json`
- `configs/model/evidence/t12_cluster_inference_environment.json`
- `configs/model/evidence/t12_cluster_checkpoint_snapshot.json`
- `docs/decisions/ADR_T12_cluster_inference_architecture.md`
- `docs/decisions/DEV-20260711-001_pre_t12_execution_order_deviation.md`
