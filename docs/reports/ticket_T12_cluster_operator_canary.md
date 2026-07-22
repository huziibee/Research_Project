# T12 Cluster Operator Canary Evidence

**Ticket:** T12
**Stage:** I — local Slurm operator canary
**Status:** PASS
**Measurement timestamp:** 2026-07-22T06:07:25Z

## Scope

Lightweight CPU-only operator/infrastructure canary. No GPU, no model load, no
torch/transformers/vLLM, no protected or annotation data.

## Operator and source

| Field | Value |
|---|---|
| Operator commit | `fe85d8c822fb48f5fea77817b8a99251c61dc378` |
| Feature commit (operator) | `8fc6effb322834f3ec120ea7341b1f6fce8787e0` |
| Archive | `t12-fe85d8c.tar.gz` |
| Archive SHA-256 | `3dafc8e3021b94632926694904ee92a3250ed3cb9be9653e66550f2169fb8388` |
| Archive bytes | 228539946 |
| Transfer | `git_archive` |

## Run

| Field | Value |
|---|---|
| Run ID | `t12-canary-20260722T060451Z-fe85d8c` |
| Slurm job | 4122 |
| Partition | `stampede` |
| Node | `mscluster40` |
| Terminal state | `COMPLETED` |
| Exit code | `0:0` |
| Remote result (sanitised) | `${T12_CLUSTER_ROOT}/runs/t12-canary/t12-canary-20260722T060451Z-fe85d8c` |
| Local pull | `outputs/t12_cluster_jobs/t12-canary-20260722T060451Z-fe85d8c/pulled` |

## Verification

Independent local `--verify latest` recomputed SHA-256, sizes, and JSONL row
counts. Result: **VERIFY_PASSED**.

Expected files present:

- `canary_result.json`
- `canary_records.jsonl`
- `run_manifest.json`
- `source_identity_manifest.json`

## Safety

- GPU required: false
- Model loaded: false
- Protected data used: false
- `selected_model`: null

This canary does not change the D-Final terminal `candidate_rejected` outcome.
