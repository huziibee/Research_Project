# T12 Stage C2A — Persistent vLLM batch backend and shard runner

**Ticket:** T12
**Stage:** C2A (persistent direct-Python vLLM batch backend, mocked CPU validation)
**Date:** 2026-07-11
**Authority:** DEV-20260711-001
**Status:** Stage C2A ready for review — Stage C **not** complete

## 1. Scope

Stage C2A delivers:

- lazy-load vLLM batch backend with persistent engine lifecycle;
- batch request/result contracts with output normalisation;
- ModelClient-compatible `generate_json` wrapper (raw output only);
- one-shard batch runner integrating C1 preflight, resume, and atomic outputs;
- multiprocess-safe CLI entrypoint;
- Slurm template wiring for future cluster execution;
- CPU-only mocked tests without local vLLM installation.

## 2. Non-scope (explicit)

Stage C2A does **not**:

- connect through SSH;
- execute `srun` / `sbatch`;
- invoke Apptainer;
- import vLLM during ordinary package import;
- require vLLM locally;
- instantiate a real engine in tests;
- load Qwen3-8B weights;
- implement Qwen3 thinking disablement;
- implement schema-v2 prompts or structured JSON decoding;
- implement repair attempts;
- execute the frozen 10-fixture bake-off;
- claim Stage C or T12 complete.

Stage C2B will perform controlled live cluster integration.

## 3. Governance boundary

- T11 remains **BLOCKED**.
- DEV-20260711-001 authorises synthetic-only preparatory work.
- No protected data, research-pool records, T13, or T14 work.
- `model_licence_register.selected_model` remains `null`.
- Model candidate status remains `provisionally_selected_for_cluster_validation`.
- No model was loaded. No SSH or Slurm actions occurred.

## 5. Initial failing tests (output-correlation correction red phase)

Before positional output-correlation correction, new tests failed because the backend
required vLLM engine `request_id` values to match batch indices or caller IDs:

```text
test_opaque_engine_ids_map_positionally
  AssertionError: 'failure' != 'success'

test_numeric_engine_ids_do_not_produce_unknown_output_id
  AssertionError: 'failure' != 'success'

test_four_requests_in_two_backend_calls_correlate_correctly
  AssertionError: False is not true

test_more_outputs_than_inputs_fail_explicitly
  AssertionError: 'excess_engine_output' not found in 'missing_engine_output'

test_engine_output_order_mismatch_when_caller_id_at_wrong_position
  AssertionError: 'engine_output_order_mismatch' not found in 'unknown_output_id'

test_string_numeric_engine_ids_map_positionally
  AttributeError: 'BatchGenerationResult' object has no attribute 'engine_request_id'
```

Root cause: after positional mapping, `generate_batch()` compared each engine
`request_id` against `{str(index), request.request_id}` and overwrote successful
results with `unknown_output_id` when vLLM returned opaque or globally numbered IDs.

## 5. Initial failing tests (manifest-identity correction red phase)

Before manifest-identity correction, new tests failed because required fields were not persisted or compared:

```text
TypeError: write_shard_outputs() missing required arguments: 'model_repository', 'backend_config_hash'

test_completed_manifest_persists_model_repository
  AssertionError: '' != 'Qwen/Qwen3-8B'

test_different_model_repository_blocks_completed_conflict
  # evaluate_resume skipped repository check entirely

test_successful_retry_preserves_prior_failure_entry
  AssertionError: 0 == 1  # attempt_history empty after retry
```

## 5. Initial failing tests (conflict-safety correction red phase)

Before the completed-shard conflict correction, new tests failed because incompatible completed shards were overwritten:

```text
# test_incompatible_completed_shard_blocks_without_backend
AssertionError: 'completed' != 'blocked'

# test_corrupted_completed_output_hash_blocks_without_backend
AssertionError: 2 != 1  # backend started twice

# ImportError until ShardRunDecision added to run_state.py
ImportError: cannot import name 'ShardRunDecision'
```

Root cause: `batch_runner.py` set `resume_allows_overwrite = not decision.skip`, passing `allow_overwrite=True` to `write_shard_outputs` whenever `evaluate_resume` returned any non-skip reason—including incompatible completed-shard mismatches.

## 5. Initial failing tests (TDD red phase — original C2A)

Before implementation, all three new Stage C2A test modules failed on import:

```text
ModuleNotFoundError: No module named 'ambiguity_manager.model.backends.vllm_batch'
ModuleNotFoundError: No module named 'ambiguity_manager.model.cluster.batch_runner'
FileNotFoundError: scripts/t12_cluster_run_batch.py
```

Representative command:

```powershell
$env:PYTHONPATH = "src"
python -m unittest tests.test_t12_vllm_batch_backend -v
# ModuleNotFoundError for vllm_batch module
```

## 5. Backend lifecycle

States: `created` → `started` → `closed` (or `failed` on startup error).

- Constructor does not load the model.
- `start()` creates the engine once (lazy vLLM import or injected factory).
- Repeated `start()` is idempotent.
- Multiple `generate_batch()` calls reuse the same engine.
- Generation before `start()` raises `backend_not_started`.
- Startup failure sets lifecycle to `failed` and leaves the backend unusable.
- GPU memory release is not claimed without process exit.

## 6. Lazy dependency loading

- No top-level `import vllm`.
- vLLM is loaded via `importlib.import_module("vllm")` only inside `_import_vllm_module()` when real startup is requested without an injected factory.
- `ImportError` becomes a precise `ModelBackendUnavailableError`; other startup exceptions become `VllmBatchBackendError`.
- Importing `ambiguity_manager.model` does not load `torch`, `vllm`, or `transformers`.

## 7. Persistent-engine contract

Cluster execution model:

```text
one Slurm task → one Python process → one persistent vLLM engine → multiple generation batches
```

Architectural defaults (from runtime config):

- direct Python vLLM API (not OpenAI-compatible server as primary path);
- `tensor_parallel_size = 1`;
- offline-only, no network fallback;
- one independent replica per node; data-parallel scaling via independent Slurm jobs/shards.

## 8. Batch input contract

Each `BatchRequest` contains:

- `request_id`, `prompt`, `ordinal`, `synthetic`, optional `metadata`.

Validation before engine invocation:

- duplicate IDs rejected;
- blank prompts rejected;
- missing/negative ordinals rejected;
- non-synthetic requests rejected;
- prompts are not built or altered by the backend.

## 9. Batch result contract

Each `BatchGenerationResult` records:

- request ID, ordinal, raw text (preserved exactly);
- optional `engine_request_id` diagnostic (vLLM internal ID; not canonical);
- backend identifier, model repository/revision, config hash;
- generation status, finish reason;
- prompt/completion token counts when available (`null` otherwise);
- latency when supplied;
- error type/message on failure.

Output ordering follows input ordinal. Missing, excess, malformed, or multi-completion
engine outputs become explicit failure records. Positional correlation uses documented
vLLM output order; engine request IDs are diagnostic only.

## 10. Engine output normalisation

`normalize_engine_output()` accepts documented vLLM-like shapes:

- objects with `.outputs` list;
- dict payloads with `"outputs"` key;
- completions with `.text` / `"text"`, optional token counts and finish reason.

Policy: exactly **one** completion per request. Multiple completions → `multiple_completions` failure.

### 10.1 Output correlation contract (C2A correction)

For the direct Python `LLM.generate()` path, vLLM returns an ordered sequence of
`RequestOutput` objects corresponding to the submitted prompt order. Project request
correlation therefore uses **output position**, not vLLM's internal `request_id`:

- caller `request_id` values remain canonical in every `BatchGenerationResult`;
- caller ordinals are preserved unchanged;
- raw generated text is preserved exactly;
- vLLM's `RequestOutput.request_id` is retained only as optional diagnostic metadata
  (`engine_request_id` on `BatchGenerationResult`; `null` when absent);
- numeric, numeric-string, and opaque engine IDs must not produce `unknown_output_id`;
- the backend must not require engine IDs to equal caller IDs or batch indices.

Positional correlation is permitted only when:

- the engine returned a sequence;
- output count exactly equals input count;
- each output element is structurally valid;
- every output contains exactly one completion;
- each completion contains usable generated text or an explicit failure record;
- input request IDs were unique before invocation.

Fail closed when:

- output count is lower than input count → `missing_engine_output`;
- output count is higher than input count → `excess_engine_output`;
- output is not a sequence → `malformed_engine_output`;
- an output element is malformed → `malformed_engine_output`;
- an output contains zero completions → `malformed_engine_output`;
- an output contains multiple completions → `multiple_completions`.

Optional consistency protection: if an engine `request_id` exactly equals one of the
caller request IDs but appears at the wrong position, the backend fails with
`engine_output_order_mismatch`. Ordinary numeric/internal engine IDs do not trigger
this failure.

### 10.2 Live C2B observation motivating the correction

Stage C2B live smoke (2026-07-11) on vLLM 0.20.1 inside the pinned SIF observed that
engine outputs may carry numeric/internal `request_id` values that do not match batch
indices. The pre-correction C2A backend rejected those as `unknown_output_id` when
`batch_size > 1`. C2B used a cluster-side instrumented driver workaround (not
committed) to map outputs positionally for bounded smoke only. That workaround is
superseded by this committed correction. **C2B must be rerun from a new committed
source SHA before Stage C2B acceptance.**

## 11. ModelClient compatibility

`VllmBatchBackend.generate_json()` implements the existing `ModelClient` protocol:

- extracts user message content as prompt;
- requires `metadata["synthetic"] == True`;
- returns `GenerateJsonResult` with raw output preserved;
- does **not** parse or validate schema-v2 JSON (Stage D responsibility).

## 12. Runner orchestration

`run_shard_batch()` in `batch_runner.py`:

1. validates preflight PASS and `full_sha256` integrity;
2. loads runtime config and shard plan;
3. requires synthetic declaration and per-record synthetic markers;
4. evaluates resume identity and classifies shard state via `ShardRunDecision` before backend startup;
5. starts one persistent backend (or injected fake);
6. sends records in bounded batches via backend;
7. records success or failure for every input;
8. writes outputs through C1 atomic-output protocol;
9. returns non-complete status when any generation fails or output is incomplete.

## 13. Resume and atomic-output integration

Uses C1 `evaluate_resume`, `write_shard_outputs`, and `ResumeIdentity` with explicit `ShardRunDecision` classification.

### 13.1 ShardManifest identity fields

`ShardManifest` now persists all frozen shard identities required for exact resume:

- run ID, shard ID, input-plan hash, input-shard hash, expected record IDs;
- output record count, output SHA-256;
- backend identifier, backend/config hash;
- model repository, model revision, container SHA;
- completion status, `retry_count`, `failure_reasons`, and `attempt_history`.

Only immutable repository identifiers and deterministic configuration hashes are stored — not full configuration contents.

### 13.2 Exact completed-shard compatibility

Exact skip (`SKIP_EXACT_COMPLETED`) is permitted only when **every** persisted identity matches the current `ResumeIdentity`, including `model_repository`, `backend_config_hash`, and `backend_identifier`.

Deterministic mismatch reasons include:

- `completed_conflict:model_repository`
- `completed_conflict:model_revision`
- `completed_conflict:backend_config_hash`
- `completed_conflict:backend_identifier`
- `completed_conflict:container_sha256`

### 13.3 Missing-identity backward-compatibility policy

No Stage C production output exists yet; validation is not weakened for identity-incomplete manifests.

- Completed manifest missing a required identity field → `BLOCK_CORRUPTED_COMPLETION` (e.g. `corrupted_completion:missing_model_repository`); no silent inference from current runtime configuration.
- Failed/incomplete manifest missing required identity → `BLOCK_IDENTITY_MISMATCH` (e.g. `identity_mismatch:missing_backend_config_hash`); not retryable.
- Manifests are never auto-upgraded by guessing values.

### 13.4 Failed/incomplete retry identity

Failed or incomplete shards are retryable only when immutable identities match, including `model_repository`, `backend_config_hash`, `backend_identifier`, `model_revision`, and `container_sha256`. Different repository or config hash → `BLOCK_IDENTITY_MISMATCH`.

### 13.5 Attempt history

`retry_count` alone is insufficient. Each manifest carries an append-only `attempt_history` of superseded attempts. Each entry records:

- attempt number, status, start/end timestamps;
- failure reasons, output count, output SHA-256;
- prior manifest SHA-256, parsed-output path reference (no raw generated text);
- backend/config hash, backend identifier, model repository/revision, container SHA.

On retry: prior manifest is hashed, appended to history, outputs written atomically, final manifest written only after validation. Successful completion preserves all prior failure entries. `retry_count == len(attempt_history)`.

### 13.6 Conflict and overwrite policy

- **Exact completed compatible shard** → `SKIP_EXACT_COMPLETED`: skip without engine startup; no output or manifest modification.
- **Incompatible completed shard** → `BLOCK_COMPLETED_CONFLICT`: fail closed; bytes and attempt history preserved.
- **Corrupted completion evidence** → `BLOCK_CORRUPTED_COMPLETION`: fail closed; not an ordinary rerunnable failure.
- **Failed/incomplete shard with matching identity** → `RETRY_FAILED` / `RETRY_INCOMPLETE`: backend may start; overwrite only for non-completed prior state.
- **Identity mismatch on non-completed shard** → `BLOCK_IDENTITY_MISMATCH`.
- **New run** → `RUN_NEW`.
- **Temporary files** (`.tmp` or dot-prefix) are never treated as completed.
- **Completed outputs are never silently overwritten.** C2A provides **no general force-overwrite or identity-bypass option**.

## 14. Slurm template changes

`configs/cluster/t12_inference.sbatch` now:

- exports `VLLM_WORKER_MULTIPROC_METHOD=spawn`;
- writes preflight result to explicit path;
- invokes `scripts/t12_cluster_run_batch.py` with explicit runtime config, shard plan, shard ID, run directory, input JSONL, and synthetic declaration paths.

Retained: `biggpu`, exclusive allocation, no `--gres`, no `--nodelist`, job-local `/var/tmp`, offline flags, `${T12_HF_CACHE}/hub`, no personal paths or credentials.

## 15. Unverified runtime parameters

Generation and engine settings in `configs/cluster/t12_vllm_batch_runtime.json` are labelled:

`verification_status: unverified_until_stage_c2b`

Stage C2B must live-verify tuning before production cluster acceptance.

## 16. Required Stage C2B live checks

- Real vLLM engine startup inside Apptainer on allocated Blackwell node;
- Fresh SIF full SHA-256 recomputation gate;
- Live runtime-facts probe feeding preflight;
- End-to-end synthetic shard execution on cluster hardware;
- GPU memory and batch-size tuning validation;
- Controlled integration smoke while T11 remains BLOCKED.

## 17. No-model-load statement

No model weights were loaded. No vLLM engine was started. No GPU tests were run.

## 18. No-SSH / no-Slurm statement

No SSH connections were made. No Slurm jobs were submitted or executed.

## 19. Test results

Commands (2026-07-11):

```powershell
$env:PYTHONPATH = "src"
python -m unittest tests.test_t12_vllm_batch_backend -v
python -m unittest tests.test_t12_cluster_batch_runner -v
python -m unittest tests.test_t12_cluster_run_batch_cli -v
python -m unittest tests.test_t12_cluster_slurm_template -v
```

Result: **52 C2A-related tests, OK**

```powershell
python -m unittest discover -s tests -p "test_t12_*.py"
```

Result: **376 tests, OK (skipped=2)**

```powershell
python -m unittest tests.test_governance_ethics tests.test_governance_deviations tests.test_governance_model_licence tests.test_governance_repo_smoke
```

Result: **31 tests, OK**

Import isolation (fresh process):

```powershell
python -c "import sys; import ambiguity_manager.model; print('torch', 'vllm', 'transformers'); print('torch' in sys.modules, 'vllm' in sys.modules, 'transformers' in sys.modules)"
# torch vllm transformers
# False False False
```

CLI `--help` verified for all four cluster scripts.

## 20. Explicit status

**Stage C2A:** READY FOR REVIEW
**Stage C:** NOT COMPLETE (C2B live integration pending)
**Stage D:** NOT STARTED
**T12:** NOT COMPLETE
**T11:** BLOCKED (unchanged)
