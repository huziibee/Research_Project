# Model candidate bake-off operator runbook

Development-only workflow for running allowlisted base-model candidates through preflight, transport smoke, and full bake-off on the Wits MSCluster Slurm path. Uses the local operator CLI (`scripts/t12_cluster_job.py`); do not use interactive SSH as the primary workflow.

## Prerequisites

- Clean git tree on branch `feature/t12-cluster-redesign` (operator enforces this).
- SSH alias `wits-mscluster` configured with BatchMode.
- Cluster root via `T12_CLUSTER_ROOT` (default `$HOME/t12-hpc` on cluster).
- Allowlisted candidate IDs only: `qwen3_8b`, `phi4_14b`, `mistral_small_24b_2501` (from `configs/model/base_model_candidates_v1.json`).
- Pinned runtime: `vllm-openai-v0.20.1.sif` (sha256 `d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1`).

## Stage 0 — Preflight (per candidate)

Checks metadata, revision, licence, tokenizer load, structured-output construction, and memory/runtime compatibility without full generation.

```bash
python scripts/t12_cluster_job.py \
  --run model_candidate_preflight \
  --candidate-id qwen3_8b \
  --poll --pull
```

Verify pulled evidence:

```bash
python scripts/t12_cluster_job.py --verify latest
```

Expected files: `preflight_result.json`, `candidate_provenance.json`, `run_manifest.json`, `source_identity_manifest.json`.

## Stage 1 — Transport smoke (per candidate)

Exactly four frozen records from `data/development/model_selection_v1/transport_smoke_ids.json`. Requires 4/4 attempted, strict structured output, raw attempts retained, no unconstrained fallback.

```bash
python scripts/t12_cluster_job.py \
  --run model_candidate_transport_smoke \
  --candidate-id qwen3_8b \
  --poll --pull
```

Check `transport_smoke_summary.json` for `status: pass` before proceeding to bake-off.

## Stage 2 — Full development bake-off

Full 40-record frozen set; generates `full_context` and `context_blind` analyses. Metrics in `metrics_summary.json` are eligibility-aware and development-only (not official claims).

```bash
python scripts/t12_cluster_job.py \
  --run model_candidate_bakeoff \
  --candidate-id qwen3_8b \
  --poll --pull
```

## Operator commands

| Action | Command |
|--------|---------|
| Submit only | `python scripts/t12_cluster_job.py --run <profile> --candidate-id <id>` |
| Status | `python scripts/t12_cluster_job.py --status latest` |
| Poll | `python scripts/t12_cluster_job.py --poll latest --pull` |
| Pull | `python scripts/t12_cluster_job.py --pull <run_id>` |
| Verify manifest | `python scripts/t12_cluster_job.py --verify <run_id>` |
| List runs | `python scripts/t12_cluster_job.py --list` |
| Dry-run packaging | `python scripts/t12_cluster_job.py --run canary --dry-run` |

## Profiles

| Profile | GPU | Purpose |
|---------|-----|---------|
| `canary` | no | CPU infrastructure canary (unchanged) |
| `model_candidate_preflight` | yes (`biggpu`, exclusive) | Candidate preflight |
| `model_candidate_transport_smoke` | yes | 4-record transport |
| `model_candidate_bakeoff` | yes | Full development bake-off |

## Safety notes

- Operator refuses existing remote result directories (no `rm -rf` cleanup).
- Candidate CLI args must be allowlisted IDs, not arbitrary Hugging Face repo strings.
- `selected_adapter` and `selected_model_strategy` remain null until official selection stages.
- No protected labels or source gold labels are included in prompts.
