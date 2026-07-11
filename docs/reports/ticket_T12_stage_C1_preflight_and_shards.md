# T12 Stage C1 — Cluster preflight and resumable shard infrastructure

**Ticket:** T12  
**Stage:** C1 (preflight, sharding, atomic outputs, resume, merge, Slurm template validation)  
**Date:** 2026-07-11  
**Authority:** DEV-20260711-001  
**Status:** Stage C1 ready for review — Stage C **not** complete

## 1. Scope

Stage C1 delivers backend-neutral, CPU-testable cluster execution infrastructure:

- runtime preflight validation against pinned configs;
- standard-library snapshot inventory verification;
- deterministic shard planning;
- atomic shard output protocol;
- resume identity checks;
- deterministic shard merge validation;
- Slurm job template and JSON placeholder contract;
- CLI wrappers for preflight, shard preparation, and merge.

## 2. Non-scope (explicit)

Stage C1 does **not**:

- import or invoke vLLM;
- instantiate an LLM engine;
- load Qwen3-8B weights;
- invoke Apptainer;
- execute `srun` / `sbatch`;
- connect through SSH;
- submit Slurm jobs;
- access the network;
- create research-data shards;
- implement Stage D prompt or structured decoding;
- edit schema-v2 enum definitions;
- modify `worker_process.py`;
- claim Stage C or T12 complete.

Stage C2 will implement the persistent vLLM batch backend and controlled cluster integration.

## 3. Governance boundary

- T11 remains **BLOCKED**.
- DEV-20260711-001 authorises this preparatory synthetic-only work.
- No protected data, research-pool records, T13, or T14 work.
- `model_licence_register.selected_model` remains `null`.
- Model candidate status remains `provisionally_selected_for_cluster_validation`.
- No model was loaded. No SSH or Slurm actions occurred.

## 4. Initial failing tests (TDD red phase)

Before implementation, all six new Stage C1 test modules failed on import:

```text
ModuleNotFoundError: No module named 'ambiguity_manager.model.cluster.preflight'
ModuleNotFoundError: No module named 'ambiguity_manager.model.cluster.snapshot_verify'
ModuleNotFoundError: No module named 'ambiguity_manager.model.cluster.sharding'
ModuleNotFoundError: No module named 'ambiguity_manager.model.cluster.atomic_outputs'
ModuleNotFoundError: No module named 'ambiguity_manager.model.cluster.run_state'
FileNotFoundError: configs/cluster/t12_inference.sbatch (Slurm template tests)
```

Representative command:

```powershell
$env:PYTHONPATH = "src"
python -m unittest tests.test_t12_cluster_preflight -v
# ImportError / ModuleNotFoundError for preflight module
```

## 5. Implementation summary

| Area | Module / artefact |
|------|-------------------|
| Config loading | `src/ambiguity_manager/model/cluster/_config_loader.py` |
| Preflight | `src/ambiguity_manager/model/cluster/preflight.py` |
| Snapshot verify | `src/ambiguity_manager/model/cluster/snapshot_verify.py` |
| Sharding | `src/ambiguity_manager/model/cluster/sharding.py` |
| Atomic outputs | `src/ambiguity_manager/model/cluster/atomic_outputs.py` |
| Resume / merge | `src/ambiguity_manager/model/cluster/run_state.py` |
| CLI | `scripts/t12_cluster_preflight.py`, `scripts/t12_prepare_synthetic_shards.py`, `scripts/t12_merge_cluster_shards.py` |
| Templates | `configs/cluster/t12_inference.sbatch`, `configs/cluster/t12_inference_job.template.json` |

Package exports extended in `src/ambiguity_manager/model/cluster/__init__.py`.

## 6. Preflight contract

`run_preflight(runtime_facts)` validates caller-supplied facts against:

- `configs/model/immutable_selection.json`
- `configs/model/cluster_execution_policy.json`
- `configs/environments/t12_cluster_inference.json`

Machine-readable result fields include status, caller timestamp, hostname, partition, exclusivity, GPU/VRAM/compute capability, driver, CUDA availability, container path/size/SHA method, model repository/revision, snapshot inventory, offline-resolution result, effective `HF_HOME` and Hub cache, rejection reasons, warnings, and config hashes.

Runtime facts are never fabricated by the library.

### Node allowlist and denylist semantics

The active execution policy retains `"node_allowlist": []` — no permanent exact-node requirement. An empty allowlist does **not** pin an exact node; denylist and all other policy checks still apply.

| Policy shape | Schema validation | Runtime behaviour |
|--------------|-------------------|-------------------|
| Empty allowlist | Valid | Any non-denied allocated node may pass when all other checks pass |
| Singleton allowlist | Valid (future configuration) | Only the listed node may pass; unlisted nodes fail with `node_allowlist_mismatch` |
| Multi-node allowlist | Valid (future configuration) | Any listed node may pass; unlisted nodes fail with `node_allowlist_mismatch` |
| Denylist | Valid (including singleton) | Takes precedence over allowlist; denied nodes fail with `denied_node` even when allowlisted |
| Overlap in allowlist and denylist | Rejected at schema validation | Not reached at runtime |

Schema validation and runtime preflight agree on these semantics. Both `node_allowlist` and `node_denylist` must be lists of non-empty strings without leading or trailing whitespace, without duplicate entries, and without contradictory overlap between the two lists.

Optional configured allowlists are supported at runtime. Production preflight logic does not hardcode cluster node names.

**C1 correction (2026-07-11):** An earlier implementation incorrectly rejected every singleton allowlist with `exact_node_required_by_allowlist` at runtime. That behaviour was removed; singleton and multi-node allowlists are now enforced by membership check only.

**C1 policy-schema correction (2026-07-11):** The execution-policy schema validator previously rejected singleton allowlists containing `mscluster112` with `node_allowlist must not permanently require one exact node`. That hardcoded restriction was removed. Singleton and multi-node allowlists are valid configuration shapes; runtime membership is enforced only when the allowlist is non-empty.

## 7. Full-hash versus sidecar distinction

Container integrity methods are represented distinctly:

- `full_sha256`
- `sidecar_sha256`
- `size_only`
- `not_checked`

Only `full_sha256` satisfies the Stage C runtime-integrity gate. B3 sidecar evidence (`size_and_sidecar_match`) remains valid historical evidence and is **not** upgraded automatically.

## 8. Corrected HF cache semantics

Preflight enforces:

- `effective_hf_home` = `${T12_HF_CACHE}` (parent root)
- `effective_hub_cache` = `${T12_HF_CACHE}/hub`
- `network_fallback` = false
- offline resolution passed

This matches the B2R corrective finding documented in `docs/reports/ticket_T12_stage_b2_live_verification.md`.

## 9. Snapshot verifier

`verify_snapshot(path)` uses the standard library only:

- follows symlinks;
- reports broken links, resolved file count, total bytes, safetensors shard count;
- checks required filenames and revision directory name;
- validates Hub-cache path relationship;
- returns deterministic sorted filenames.

Canonical acceptance inventory (cluster):

| Field | Value |
|-------|-------|
| repository | `Qwen/Qwen3-8B` |
| revision | `b968826d9c46dd6066d109eabc6255188de91218` |
| resolved files | 15 |
| resolved bytes | 16397461266 |
| safetensors shards | 5 |

No `refs/` directory is required. Hugging Face Hub is not imported in CPU unit tests.

## 10. Shard assignment method

Method: **`ordinal_contiguous_balanced`**

1. Assign explicit ordinals during JSONL ingestion.
2. Fail closed on duplicate or malformed IDs.
3. Partition records contiguously into `shard_count` buckets.
4. Balance sizes so counts differ by at most one.

Input and per-shard hashes use SHA-256 over deterministic JSON lines. Python's built-in `hash()` is not used.

## 11. Atomic-output protocol

- Write to a temp file in the destination directory.
- Flush and `fsync`.
- Validate completed temp output.
- Atomically replace final path via `os.replace`.
- Write completion manifest only after final output validation.
- `.tmp` / hidden temp files are never treated as complete.
- Valid completed shards are not overwritten unless explicitly configured.
- Conflicting run IDs or input hashes are refused.

## 12. Resume identity rules

A shard may be skipped only when **all** of the following match:

- run ID, shard ID, input-plan hash, input-shard hash;
- expected record IDs, output record count, output SHA-256;
- model revision, container SHA, backend/config hash;
- completion status `completed`.

Any mismatch returns a deterministic reason and requires a new run ID or explicit recovery. Failed shards are resumable but not skippable. Partial temp files are not complete.

## 13. Deterministic merge rules

Merge accepts only compatible completed shards with identical run/model/container identities, rejects duplicate/missing/unexpected IDs, restores plan record order, writes output atomically, and records merged SHA-256 plus input shard hashes. Repeated merges produce identical merged hashes.

## 14. Slurm template contract

`configs/cluster/t12_inference.sbatch` includes:

- `#!/usr/bin/env bash`, `set -euo pipefail`
- partition `biggpu`, exclusive allocation, one node/task
- configurable CPU/memory/time via environment variables
- no `--gres`, no `--nodelist`, no personal paths or credentials
- offline flags and `${T12_HF_CACHE}` / `${T12_HF_CACHE}/hub` semantics
- `/var/tmp/${USER}-apptainer-${SLURM_JOB_ID}` with job-local cleanup trap
- preflight before future model execution
- explicit Stage C2 comment for persistent vLLM engine

Template is validated only; not executed.

## 15. No-model-load statement

No model weights were loaded. No vLLM engine was started. No GPU tests were run.

## 16. No-SSH / no-Slurm statement

No SSH connections were made. No Slurm jobs were submitted or executed.

## 17. Remaining Stage C2 work

- Implement `src/ambiguity_manager/model/backends/vllm_batch.py` persistent engine backend.
- Wire preflight + shard execution inside Apptainer on cluster hardware.
- Live runtime-facts probe gathering GPU/container facts on allocated nodes.
- Fresh SIF full SHA-256 recomputation gate on cluster.
- Controlled cluster integration smoke (still synthetic-only while T11 is BLOCKED).

## 18. Test results

Commands (2026-07-11):

```powershell
$env:PYTHONPATH = "src"
python -m unittest tests.test_t12_cluster_preflight -v
python -m unittest tests.test_t12_cluster_snapshot_verify -v
python -m unittest tests.test_t12_cluster_sharding -v
python -m unittest tests.test_t12_cluster_atomic_outputs -v
python -m unittest tests.test_t12_cluster_resume -v
python -m unittest tests.test_t12_cluster_slurm_template -v
```

Result: **68 tests, OK (skipped=1)** — broken-symlink test skipped on Windows without symlink privilege.

```powershell
python -m unittest discover -s tests -p "test_t12_*.py"
```

Result: **313 tests, OK (skipped=2)**

```powershell
python -m unittest tests.test_governance_ethics tests.test_governance_deviations tests.test_governance_model_licence tests.test_governance_repo_smoke
```

Result: **31 tests, OK**

CLI `--help` verified for all three new scripts.

## 19. Explicit status

**Stage C1:** READY FOR REVIEW  
**Stage C:** NOT COMPLETE (C2 backend pending)  
**T12:** NOT COMPLETE  
**T11:** BLOCKED (unchanged)
