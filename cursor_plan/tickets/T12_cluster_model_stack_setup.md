# T12 — Cluster model stack setup (Stages A–I)

**Status:** ACTIVE  
**ADR:** `docs/decisions/ADR_T12_cluster_inference_architecture.md`  
**Supersedes:** `cursor_plan/tickets/T12_local_text_model_and_training_stack_setup.md`  
**Archive branch:** `archive/t12-local-wsl-slice4`  
**Forward-migration base:** `b4865b3a101c87b7b5fe468c12c40adead74068f`  
**Governance:** T11 remains **BLOCKED**; `DEV-20260711-001` permits T12 preparatory work only

## Cluster-validation model (provisional)

| Field | Value |
|---|---|
| Model ID | `Qwen/Qwen3-8B` |
| Immutable revision SHA | `b968826d9c46dd6066d109eabc6255188de91218` |
| Candidate status | `provisionally_selected_for_cluster_validation` |
| Inference container | `vllm-openai-v0.20.1.sif` |
| Container SHA-256 | `d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1` |
| `selected_model` | `null` until Stage I |

## Shared governance limits (all stages)

- T11 verdict remains **BLOCKED**; do not set `collection_permitted: true`.
- No T13 or T14 progression.
- No protected data or full research-pool execution.
- No optimiser steps on research records except Stage F zero-step feasibility probe.
- No change to `model_licence_register.selected_model` until Stage I.
- No local model weight or environment deletion until Stage I cleanup gate.
- Synthetic fixtures and synthetic corpora only while T11 is BLOCKED.

---

## Stage A — Preservation and cluster architecture ADR

### Objective

Document the cluster-native redesign, supersede the local ticket, preserve historical WSL evidence policy, and lock planning contracts with CPU tests.

### Files to create

- `docs/decisions/ADR_T12_cluster_inference_architecture.md`
- `cursor_plan/tickets/T12_cluster_model_stack_setup.md`
- `configs/model/evidence/historical/README.md`
- `tests/test_t12_cluster_adr_references.py`

### Files to modify

- `cursor_plan/04_hardware_model_strategy.md`
- `cursor_plan/05_master_execution_plan.md` (T12 portions only)
- `cursor_plan/tickets/T12_local_text_model_and_training_stack_setup.md` (supersession notice only)

### Files not to touch

- `src/ambiguity_manager/model/**`
- `configs/licences/model_licence_register.json`
- `configs/governance/**`
- `configs/environments/**`
- `requirements/**`
- `scripts/t12_*`
- `tests/fixtures/schema_v2/t12_synthetic_inputs.jsonl`
- schema-v2 implementation files

### Red tests

- `tests/test_t12_cluster_adr_references.py` — ADR, ticket, supersession, identities, stages, governance invariants.

### Green implementation

- Author ADR and ticket; add historical README; update planning docs; implement reference tests.

### Refactor checks

- No GPU imports in Stage A tests.
- No claims of final model acceptance or that T11 has passed.

### Evidence

- ADR and ticket committed on `feature/t12-cluster-redesign`.
- CPU test output for ADR reference suite and governance suites.

### Acceptance criteria

- [ ] ADR exists with all required sections and non-claims.
- [ ] Stages A–I defined in this ticket.
- [ ] Old local ticket marked SUPERSEDED with cross-references.
- [ ] Historical README explains WSL evidence policy.
- [ ] `test_t12_cluster_adr_references` passes.
- [ ] Governance tests pass unchanged.
- [ ] `selected_model` remains `null`.

### Stopping conditions

Stop after documentation and CPU tests; do not connect to cluster.

### Compute category

CPU only (local development machine).

### Dependencies

- `archive/t12-local-wsl-slice4` preservation commit exists.
- `b4865b3` feature branch base.

### Proposed commit boundary

`docs(t12): add cluster architecture ADR and supersede local ticket`

---

## Stage B — Cluster manifests, immutable identities and historical evidence relocation

### Objective

Create cluster environment manifests with pinned model and container identities; relocate WSL evidence to `configs/model/evidence/historical/`.

### Files to create

- `configs/environments/t12_cluster_inference_environment.json`
- `configs/environments/t12_cluster_training_environment.json` (manifest shell; not validated until Stage F)
- `configs/model/evidence/historical/` relocated WSL evidence files
- `tests/test_t12_cluster_environment_manifests.py`

### Files to modify

- `src/ambiguity_manager/model/environment.py` (cluster manifest validation only if required)

### Files not to touch

- `configs/licences/model_licence_register.json` (`selected_model`)
- `configs/governance/**`
- Local WSL environment manifests (move, do not rewrite history)
- `scripts/t12_*` local scripts (remain on archive branch reference)

### Red tests

- Manifest tests fail until cluster identities and SHA pins are present.

### Green implementation

- Write manifests; relocate historical evidence; validate pins.

### Refactor checks

- Historical evidence paths updated in README cross-references only.

### Evidence

- Manifest JSON with exact revision and container SHA.
- Relocation manifest listing source → historical destination.

### Acceptance criteria

- [ ] Inference manifest pins `Qwen/Qwen3-8B` revision `b968826d9c46dd6066d109eabc6255188de91218`.
- [ ] Container SHA-256 matches ADR exactly.
- [ ] WSL evidence under `historical/` with README cross-reference.
- [ ] No model weights in Git.

### Stopping conditions

Stop before vLLM backend implementation (Stage C).

### Governance limits

Synthetic-only; no cluster job submission in Stage B unless manifest validation requires read-only inspection.

### Compute category

CPU (manifest authoring); optional read-only cluster path inspection.

### Dependencies

Stage A merged or committed on feature branch.

### Proposed commit boundary

`feat(t12): add cluster manifests and relocate historical WSL evidence`

---

## Stage C — vLLM batch backend, Slurm preflight, stable shards and resume

### Objective

Implement direct Python vLLM batch inference backend, Slurm preflight checks, stable shard outputs, and resume without duplicates.

### Files to create

- `src/ambiguity_manager/model/backends/vllm_batch.py`
- `src/ambiguity_manager/model/cluster_preflight.py`
- `scripts/t12_cluster_submit_batch.py`
- `scripts/t12_cluster_preflight.py`
- Slurm job templates under `configs/cluster/`
- `tests/test_t12_cluster_preflight.py`
- `tests/test_t12_vllm_batch_shard.py` (mocked; no GPU in CI)

### Files to modify

- `src/ambiguity_manager/model/environment.py`
- `src/ambiguity_manager/model/worker_process.py` (if shared orchestration needed)

### Files not to touch

- `configs/governance/**`
- Research-pool fixtures
- Local WSL backend code on archive branch

### Red tests

- Preflight and shard-resume tests fail until backend exists.

### Green implementation

- vLLM batch path; atomic shard writes; resume logic.

### Refactor checks

- One persistent engine per GPU per job step documented in runbook.

### Evidence

- Preflight report JSON.
- Mocked shard resume test log.
- First cluster dry-run preflight output (no inference required for Stage C acceptance if mocked tests pass locally).

### Acceptance criteria

- [ ] Batch backend invokes vLLM inside pinned SIF.
- [ ] Slurm preflight validates partition, GPU, container SHA, model path.
- [ ] Shards written atomically; resume skips completed shard IDs.
- [ ] Data-parallel multi-node contract documented.

### Stopping conditions

Stop before full schema-v2 prompt integration (Stage D).

### Governance limits

Synthetic shard inputs only; no research pool.

### Compute category

GPU (cluster); CPU mocked tests locally.

### Dependencies

Stage B manifests.

### Proposed commit boundary

`feat(t12): add vLLM batch backend and Slurm preflight`

---

## Stage D — Full schema-v2 prompt, Qwen3 thinking disablement and structured JSON decoding

### Objective

Wire full schema-v2 prompt contract, disable Qwen3 thinking mode, and enforce structured JSON decoding with bounded repair attempts.

### Files to create

- `src/ambiguity_manager/model/prompt_builder.py` (cluster variant or extend)
- `src/ambiguity_manager/model/structured_decode.py`
- `tests/test_t12_cluster_prompt_builder.py`
- `tests/test_t12_structured_decode.py`

### Files to modify

- `src/ambiguity_manager/model/backends/vllm_batch.py`
- Prompt templates under `configs/model/prompts/`

### Files not to touch

- Schema-v2 enum definitions (authoritative Python)
- Deterministic router policy
- `model_licence_register.selected_model`

### Red tests

- Prompt and decode tests fail until thinking disablement and JSON schema constraints applied.

### Green implementation

- Full-contract prompt; structured decoding; repair loop with cap.

### Refactor checks

- Model output validated by schema-v2 Python validators, not model self-report.

### Evidence

- Decode configuration manifest.
- Sample raw and repaired outputs on synthetic inputs (retained).

### Acceptance criteria

- [ ] Qwen3 thinking mode explicitly disabled in inference config.
- [ ] Full schema-v2 fields requested in prompt.
- [ ] Structured decoding or equivalent JSON constraint active.
- [ ] Bounded repair attempts recorded per fixture.

### Stopping conditions

Stop before 10-fixture bake-off (Stage E).

### Governance limits

Synthetic inputs only.

### Compute category

GPU (cluster) for integration smoke; CPU for prompt unit tests.

### Dependencies

Stage C batch backend.

### Proposed commit boundary

`feat(t12): add schema-v2 prompt and structured JSON decoding`

---

## Stage E — Ten-fixture full-contract synthetic correctness bake-off

### Objective

Prove 10/10 schema-valid outputs on the existing synthetic fixture set with full contract enforcement.

### Files to create

- `configs/model/evidence/t12_cluster_synthetic_bakeoff.json`
- `docs/reports/ticket_T12_stage_E_bakeoff.md`
- `tests/test_t12_cluster_bakeoff_contract.py` (evidence schema tests)

### Files to modify

- `scripts/t12_run_synthetic_evaluation.py` (cluster variant)

### Files not to touch

- `tests/fixtures/schema_v2/t12_synthetic_inputs.jsonl` (fixture set frozen)
- Research pool records

### Red tests

- Bake-off evidence schema test fails until 10/10 results recorded.

### Green implementation

- Run 10 fixtures on cluster; record all raw outputs, repairs, failures.

### Refactor checks

- Semantic thresholds defined **before** viewing results.

### Evidence

- Per-fixture raw output, parse result, schema validation, repair log.
- Summary: attempted 10, schema-valid 10, zero silent-resolution violations, zero invalid enums, zero route-policy violations.

### Acceptance criteria

- [ ] 10/10 fixtures attempted.
- [ ] 10/10 schema-valid after bounded attempts.
- [ ] All raw outputs retained.
- [ ] Zero unsupported silent-resolution commitments.
- [ ] Zero invalid enum values accepted.
- [ ] Zero route-policy violations accepted.
- [ ] All failures and repairs recorded.
- [ ] Semantic thresholds defined before viewing results.

### Stopping conditions

Stop if fewer than 10/10 schema-valid; do not proceed to Stage F until resolved or deviation recorded.

### Governance limits

Synthetic fixtures only; T11 remains BLOCKED.

### Compute category

GPU (cluster).

### Dependencies

Stage D structured decoding.

### Proposed commit boundary

`evidence(t12): record Stage E ten-fixture synthetic bake-off`

---

## Stage F — Separate cluster training environment and LoRA feasibility

### Objective

Prove separate training stack can attach untrained LoRA, save adapter, reload base + adapter, run one synthetic inference, with **optimiser steps equal zero** and **research records equal zero**.

### Files to create

- Validated `configs/environments/t12_cluster_training_environment.json`
- `configs/model/evidence/t12_cluster_lora_feasibility.json`
- `scripts/t12_cluster_lora_feasibility.py`
- `tests/test_t12_cluster_lora_feasibility_evidence.py`

### Files not to touch

- Inference SIF (not used as training stack)
- Research pool
- `selected_model`

### Red tests

- Evidence schema requires `optimiser_steps: 0` and `research_records: 0`.

### Green implementation

- Training env smoke on cluster; adapter attach/save/reload; one synthetic inference.

### Refactor checks

- Tokenizer parity between inference and training manifests verified.

### Evidence

- Exact base revision match.
- Adapter save path and reload log.
- First process exits fully before reload test.

### Acceptance criteria

- [ ] Exact base revision `b968826d9c46dd6066d109eabc6255188de91218`.
- [ ] Inference/training tokenizer parity documented.
- [ ] Untrained LoRA adapter attach succeeds.
- [ ] Adapter save succeeds.
- [ ] First process exits fully.
- [ ] Base reload succeeds.
- [ ] Adapter reload succeeds.
- [ ] One synthetic inference after reload.
- [ ] Optimiser steps equal zero.
- [ ] Research records equal zero.
- [ ] Inference SIF is not treated as the training stack.

### Stopping conditions

Stop before Stage G benchmark if feasibility fails.

### Governance limits

No research data; no optimiser steps.

### Compute category

GPU (cluster, separate training environment).

### Dependencies

Stage E passed.

### Proposed commit boundary

`evidence(t12): record Stage F LoRA feasibility with zero optimiser steps`

---

## Stage G — Full-contract synthetic benchmark, interruption and recovery

### Objective

Run deterministic 100–500 record synthetic benchmark with cold/warm load, throughput, forced interruption, resume, and merged hash verification.

### Files to create

- `configs/model/evidence/t12_cluster_benchmark_corpus_manifest.json`
- Synthetic benchmark corpus generator and corpus file (100–500 records)
- `configs/model/evidence/t12_cluster_benchmark_results.json`
- `scripts/t12_cluster_benchmark.py`
- `tests/test_t12_cluster_benchmark_evidence.py`

### Files not to touch

- Research pool
- Any 25,000-record production estimate documents (must not claim verified throughput)

### Red tests

- Evidence requires corpus hash, generator version, fixed seed, stable record IDs.

### Green implementation

- Generate corpus; run one-node benchmark (required); optional two-node; interrupt and resume.

### Refactor checks

- Atomic shard outputs; deterministic merged output hash.

### Evidence

- Cold and warm load timings.
- Structured-decoding throughput.
- Interruption/resume log without duplicates.
- Offline model reload verification.

### Acceptance criteria

- [ ] Deterministic 100–500-record synthetic benchmark corpus.
- [ ] Generator version recorded.
- [ ] Fixed seed recorded.
- [ ] Stable record IDs.
- [ ] Corpus hash recorded.
- [ ] Cold load measured.
- [ ] Warm load measured.
- [ ] Structured-decoding throughput measured.
- [ ] Forced interruption tested.
- [ ] Resume without duplicates verified.
- [ ] Atomic shard outputs verified.
- [ ] Deterministic merged output hash verified.
- [ ] Offline model reload verified.
- [ ] One-node benchmark required; two-node optional.
- [ ] No 25,000-record estimate presented as verified until this evidence exists.

### Stopping conditions

Stop before publication (Stage H) if resume or hash checks fail.

### Governance limits

Synthetic corpus only.

### Compute category

GPU (cluster); optional multi-node.

### Dependencies

Stages C–E complete; Stage F recommended.

### Proposed commit boundary

`evidence(t12): record Stage G synthetic benchmark and recovery`

---

## Stage H — Result publication, archival and notification

### Objective

Publish results to dedicated private GitHub results repository with release assets, CPU finaliser, notifications, and verified archival states.

### Files to create

- Results repository workflow templates (documented; repo may be external)
- `scripts/t12_cluster_publish_results.py`
- `scripts/t12_cluster_package_results.py`
- `configs/model/evidence/t12_publication_manifest.json`
- `tests/test_t12_publication_states.py`
- `tests/test_t12_publication_manifest.py`

### Files not to touch

- Credentials (never in source, logs, or manifests)
- Main research repository large binaries

### Red tests

- Publication state machine tests fail until all required states handled.

### Green implementation

- Package with SHA-256 manifest; upload release assets; verify remote sizes and hashes; Slurm email test; GitHub notification workflow; optional WhatsApp.

### Refactor checks

- Cluster results retained when upload fails.

### Evidence

- Publication manifest with state transitions.
- Release asset existence and hash verification log.
- Slurm email delivery confirmation.
- GitHub notification workflow run ID.

### Acceptance criteria

- [ ] Dedicated private GitHub results repository configured.
- [ ] Small summaries and manifests committed to results repo.
- [ ] Large output bundles uploaded as release assets.
- [ ] Dependent CPU finaliser using Slurm `afterany`.
- [ ] Packaging and SHA-256 manifest generated.
- [ ] Release asset existence verified.
- [ ] Remote asset-size verification recorded.
- [ ] Hash verification recorded.
- [ ] Cluster results retained when upload fails.
- [ ] Slurm email test passed.
- [ ] GitHub notification workflow tested.
- [ ] WhatsApp optional hook documented.
- [ ] Credentials excluded from source, logs, and manifests.
- [ ] `EXTERNALLY_ARCHIVED` only when all remote assets and manifests verified.

Required states: `INFERENCE_RUNNING`, `INFERENCE_PASS`, `INFERENCE_FAILED`, `VALIDATION_PASS`, `VALIDATION_FAILED`, `PACKAGING_PASS`, `PACKAGING_FAILED`, `PUBLICATION_PASS`, `PUBLICATION_FAILED`, `NOTIFICATION_PASS`, `NOTIFICATION_FAILED`, `EXTERNALLY_ARCHIVED`.

### Stopping conditions

Stop before Stage I if publication cannot reach `EXTERNALLY_ARCHIVED` for required runs.

### Governance limits

Publish synthetic benchmark evidence only.

### Compute category

GPU (inference jobs) + CPU (finaliser packaging).

### Dependencies

Stage G benchmark artefacts.

### Proposed commit boundary

`feat(t12): add result publication and notification pipeline`

---

## Stage I — Final T12 acceptance, runbook and local-cleanup gate

### Objective

Final acceptance after all gates pass; update `selected_model` only here; document local cleanup eligibility without performing deletion.

### Files to create

- `docs/reports/ticket_T12_completion_report.md`
- `docs/runbooks/t12_cluster_operations.md`
- `configs/model/evidence/t12_local_cleanup_inventory.json`
- `tests/test_t12_completion_evidence.py`

### Files to modify

- `configs/licences/model_licence_register.json` — set `selected_model` **only if all gates pass**
- `cursor_plan/05_master_execution_plan.md` — mark T12 gate satisfied

### Files not to touch

- T11 governance verdict
- Research pool
- Local model weights (document eligibility only; deletion is separate gated task)

### Red tests

- Completion evidence test fails until all stage evidence present and cleanup inventory complete.

### Green implementation

- Aggregate evidence; write runbook; set `selected_model` if accepted.

### Refactor checks

- All CPU tests green; GPU evidence complete.

### Evidence

- Stage A–H evidence index.
- Cluster runbook verified from fresh shell.
- Local cleanup inventory listing weights and venv paths eligible for deletion.

### Acceptance criteria

- [ ] All CPU tests green.
- [ ] GPU evidence complete (Stages C–H).
- [ ] Cluster runbook works from a fresh shell.
- [ ] `selected_model` updated only here and only if all gates pass.
- [ ] T11 remains BLOCKED.
- [ ] No research pool executed.
- [ ] Local cleanup inventory completed.
- [ ] Code and Git history preserved.
- [ ] Local T12 model weights **eligible** for deletion (not deleted in Stage I).
- [ ] Local T12-specific environments **eligible** for deletion (not deleted in Stage I).
- [ ] No automatic deletion performed as part of Stage I acceptance.

### Stopping conditions

T12 complete; do not begin T13 until T11 reassessed.

### Governance limits

T11 remains BLOCKED; no research pool.

### Compute category

CPU (documentation and inventory); prior GPU evidence referenced.

### Dependencies

Stages A–H all passed.

### Proposed commit boundary

`feat(t12): complete cluster model stack acceptance and cleanup gate`

---

## Immediate local model-removal policy

Local Qwen2.5-1.5B weights and `.venv-t12-inference` / `.venv-t12-training` environments:

- **Preserved** during Stages A–H.
- **Eligible for deletion** only after Stage I cleanup gate acceptance.
- **Not deleted automatically** by any Stage A–I commit or acceptance step.
- Deletion executes through a **separate gated cleanup task** after human review of `t12_local_cleanup_inventory.json`.

Code, Git history, tests, manifests, and historical evidence under `configs/model/evidence/historical/` are **always preserved**.
