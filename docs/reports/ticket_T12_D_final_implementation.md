# T12 Stage D-Final — Integrated Structured Generation Smoke Pipeline

**Stage:** D-Final (integration only; no cluster execution, no live model/tokenizer load)
**Branch:** `feature/t12-cluster-redesign`
**Starting SHA:** `ef4e7b0124baac31a77696bb4365535b02c55067`
**Date:** 2026-07-11
**Governance:** DEV-20260711-001 (synthetic-only preparatory work; T11 remains BLOCKED)

## Compressed-stage rationale

Stage D-Final compresses the previously planned D1C2 cluster wiring and D2 live smoke preparation into one integration slice:

- production Qwen3 chat-template renderer (lazy, offline snapshot);
- run-scoped response-mode probe and verification;
- persistent vLLM generator adapter for the D1C1 pipeline;
- synthetic-only four-record cluster runner and CLI;
- CPU-only validation with injected backends/tokenizers.

No live cluster execution, model weights, or tokenizer snapshot loading occurs in this task.

## Hardening corrections (2026-07-11 review pass)

This pass corrected live-run integration defects identified during D-Final archive review.

### Cross-platform pipeline-contract identity (2026-07-11 live-smoke red evidence)

The first D-Final live run blocked on `config.pipeline_contract_hash mismatch` even though the parsed pipeline contract JSON was identical between Windows packaging and Linux extraction. Red evidence from the committed contract file:

| Identity | SHA-256 |
|---|---|
| LF raw file bytes | `94eb2d777fb6e9bbebc90b7c8d727cec2e2bebfcf0acbcd276144f2c71d34b64` |
| CRLF raw file bytes | `1c4543e29121ce1e390ea60d91c51530cb180f8624d1e7932c4d9524a186599b` |
| Canonical JSON (`canonical_json_sha256_v1`) | `786cf6e7213fa3519ba7797464c25495f790cdf4ebc0c139c433168bd703b758` |

LF and CRLF raw-byte digests represented the same parsed JSON object. Line endings and indentation are not contract semantics.

The authoritative identity is now `generation_pipeline_contract_hash()` beside `load_pipeline_contract()`, hashing `canonical_json_bytes(parsed_object)`. D-Final config records:

```json
"pipeline_contract_hash_method": "canonical_json_sha256_v1",
"pipeline_contract_hash": "786cf6e7213fa3519ba7797464c25495f790cdf4ebc0c139c433168bd703b758"
```

`run_manifest.json` retains both the canonical hash (acceptance) and optional `pipeline_contract_file_sha256` (diagnostic raw bytes).

### Config-load BLOCKED-evidence boundary

`scripts/t12_run_d_final_smoke.py` no longer calls `load_d_final_config()` before the runner. The runner creates the unique run directory first, then loads config. Config or contract-identity failures after directory creation write an honest BLOCKED package with empty JSONL files, zero engine-start count, and no fabricated response-mode verification file.

### Self-referential source-SHA defect

The prior draft committed `source_commit_sha` inside `t12_d_final_smoke.json`, creating a value that could never equal the commit containing the config. The committed config now uses:

```json
"source_identity_mode": "runtime_source_manifest_required"
```

Live runs must supply:

- `--source-identity-manifest <path>`
- `--source-archive <path>`

The runtime manifest carries `schema_version`, `source_commit_sha`, `source_archive_sha256`, `transfer_method=git_archive`, `archive_filename`, and `packaging_timestamp`. The runner validates commit/archive SHA formats, recomputes archive SHA-256, records source identity in `run_manifest.json`, and optionally cross-checks `.git` when present. Absence of `.git` does not block a valid git-archive run.

### Authoritative runtime-setting alignment

One deterministic configuration now governs the complete D-Final run:

| Setting | Value |
|---|---|
| temperature | 0.0 |
| top_p | 1.0 |
| max_tokens | 2048 |
| batch_size | 1 |
| tensor_parallel_size | 1 |
| gpu_memory_utilization | 0.9 |

Applied consistently in:

- `configs/cluster/t12_d_final_smoke.json`
- `configs/model/t12_response_mode_probe_policy.json`
- `configs/cluster/t12_stage_d_vllm_runtime.json`

The runner compares D-Final config, probe policy, and loaded vLLM runtime config and blocks on any generation/engine/batch/offline/fallback/structured-decode mismatch before tokenizer or engine startup.

### Strict raw-JSON probe acceptance

Probe acceptance no longer uses `extract_and_repair_json()` for pass/fail. Acceptance requires:

1. preserve raw output exactly;
2. strip only outer whitespace;
3. direct `json.loads`;
4. exactly one JSON object;
5. strict semantic schema validation;
6. zero local repair operations.

Diagnostics record `direct_json_parse_status`, `raw_object_status`, `local_repair_attempts`, `local_repair_log`, and `semantic_schema_status`. Repair may be logged for comparison only.

### Pre-engine full request validation

All four synthetic inputs are converted into validated `GenerationPipelineRequest` objects before tokenizer loading, backend construction, or startup. There is no implicit provenance fallback. `provenance_policy` and `label_eligibility` are strictly validated with round-trip checks; `integrity_context` is validated before startup.

### Run-scoped identity binding

`RunScopedResponseModeVerification` and `verification_matches_run()` now bind:

- evidence run ID;
- model repository and immutable revision;
- container SHA;
- tokenizer artefact hashes;
- semantic-schema hash;
- structured-decode contract hash;
- selected candidate mode.

`RunScopedVerifiedRenderer` verifies loaded tokenizer artefact hashes before emitting a verified prompt envelope.

### Actual structured-decode metadata

Probe evaluation records backend `last_structured_decode_metadata` when available. Hardcoded `unconstrained_fallback_indicated = false` was removed. Metadata must exist and match contract/schema/version/completions/construction requirements.

### Unique run-directory and BLOCKED evidence

Run directories are created with `mkdir(parents=True, exist_ok=False)`. Existing directories block before engine activity. After creation, every failure path writes a BLOCKED evidence package with consistent empty JSONL files when no attempts occurred. Required files for PASS and BLOCKED: `response_mode_probe.json`, `raw_attempts.jsonl`, `attempt_ledgers.jsonl`, `accepted_predictions.jsonl`, `record_results.jsonl`, `summary.json`, `run_manifest.json`. `response_mode_verification.json` is written only when verification was created.

### Manifest output hashing

All non-manifest evidence files are written first. `run_manifest.json` then records SHA-256, byte size, and row counts for every output file. It also records source identity, preflight hash, config hashes, structured-decode metadata, engine-start count, selected response mode, and `--slurm-log-path`.

### Expanded preflight checks

Preflight must report `status=pass`, exact model repository/revision, exact observed container SHA, `offline_resolution_passed=true`, `network_fallback=false`, and `snapshot_inventory_status=pass`. The runner does not claim offline operation from config alone.

## Implementation scope

### In scope

- `Qwen3ChatTemplateRenderer` with candidate modes `default` and `enable_thinking_false`
- frozen response-mode probe policy and deterministic first-passing selection
- run-scoped `verified_for_run` evidence object with full identity binding
- `VllmPipelineGenerator` adapter over one persistent `VllmBatchBackend`
- `run_d_final_smoke()` synthetic-only runner with fail-closed gates
- four deterministic synthetic smoke records (not Stage E fixtures)
- atomic run output layout for future live smoke
- CPU-only tests and CLI help without heavy imports

### Non-scope

- SSH, Slurm, Apptainer, or cluster execution
- real Qwen3 tokenizer/model load
- claiming live smoke passed
- semantic correctness scoring (remains `not_evaluated`)
- T19 routing / `route_policy_gate.py`
- claiming Stage D or T12 complete

## Response-mode probe design

Phase A (future live run):

1. render fixed synthetic probe command in frozen candidate order;
2. run one bounded structured-output generation per candidate via persistent backend;
3. record raw output, hashes, generation status, direct JSON/parse/schema checks, thinking-marker and prose checks;
4. apply frozen acceptance rules with zero repair tolerance;
5. select first passing candidate;
6. emit run-scoped verification evidence.

Probe policy: `configs/model/t12_response_mode_probe_policy.json`

## Deterministic mode-selection rule

Frozen candidate order:

1. `default`
2. `enable_thinking_false`

Select the first candidate passing all probe checks. If neither passes, block the four-record run.

## Four synthetic smoke inputs

File: `tests/fixtures/schema_v2/t12_d_final_smoke_inputs.jsonl`

| ID | Coverage | Expected structural disposition |
|---|---|---|
| `dfinal-001` | clear unambiguous execution | `execute` |
| `dfinal-002` | clarification-required ambiguity | `clarify` |
| `dfinal-003` | unsupported silent-resolution risk | `silent_resolution_risk` |
| `dfinal-004` | compound / multi-step structure | `multi_step` |

Input hash (frozen in config): `c20b0659793e4b1c6bf9fb7ce44a5ddd8b9e5c6214a36de1e7b5d589997102af`

## Tests and exact results

```powershell
$env:PYTHONPATH = "src"
python -m unittest tests.test_t12_qwen3_renderer -v                     → OK (32)
python -m unittest tests.test_t12_vllm_pipeline_generator -v              → OK (9)
python -m unittest tests.test_t12_cluster_generation_pipeline_runner -v → OK (28)
python -m unittest tests.test_t12_d_final_smoke_cli -v                  → OK (5)
python -m unittest tests.test_t12_attempt_evidence -v                   → OK (6)
python -m unittest tests.test_t12_repair_prompt -v                      → OK (10)
python -m unittest tests.test_t12_generation_pipeline -v                → OK (66)
python -m unittest tests.test_t12_prediction_contract -v                → OK (54)
python -m unittest tests.test_t12_prompt_builder -v                       → OK (19)
python -m unittest tests.test_t12_generation_policy -v                  → OK (11)
python -m unittest tests.test_t12_response_mode -v                      → OK (7)
python -m unittest tests.test_t12_structured_decode -v                   → OK (21)
python -m unittest tests.test_t12_vllm_batch_backend -v                   → OK (32)
python -m unittest tests.test_t12_stage_d1b1_runtime_evidence -v        → OK (22)
python -m unittest tests.test_t12_cluster_batch_runner -v               → OK (regression)
python -m unittest tests.test_t12_cluster_preflight -v                  → OK (regression)
python -m unittest tests.test_t12_cluster_run_batch_cli -v              → OK (regression)
python -m unittest discover -s tests -p "test_t12_*.py"                 → OK (744, skipped=2)
python -m unittest tests.test_governance_*                              → OK (70)
python scripts/t12_run_d_final_smoke.py --help                          → exit 0
python -c "import sys; import ambiguity_manager.model; print('torch' in sys.modules, 'transformers' in sys.modules, 'vllm' in sys.modules)"
# False False False
git diff --check → clean
```

## Explicit non-claims

D-Final implementation does **not** claim:

- a response mode passed on live output
- engine-time schema compilation passed on live hardware
- live structured output passed
- four records passed on live hardware
- semantic correctness passed
- Stage D is complete
- the live D-Final smoke passed

## Requirements for the single live D-Final smoke

1. Execute on cluster with passing preflight including offline resolution and snapshot inventory
2. Provide runtime source-identity manifest and retained git archive with matching SHA-256
3. Offline Qwen3 snapshot at pinned revision with matching D1B1 tokenizer artefact hashes
4. One persistent vLLM engine with aligned D-Final runtime settings (`t12_stage_d_vllm_runtime.json`)
5. Run response-mode probes before record pipeline; retain both raw outputs with zero repair tolerance
6. Require first passing mode in frozen order; otherwise block
7. Run exactly four committed synthetic records through D1C1 pipeline
8. Require schema-v2-valid accepted predictions and zero unsupported commitments
9. Retain all raw attempts and attempt ledgers with hashed manifest evidence
10. Record semantic correctness as `not_evaluated` only
