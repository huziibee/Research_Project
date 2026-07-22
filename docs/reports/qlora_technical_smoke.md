# QLoRA Technical Smoke (T27 Phase E)

**Status:** scaffolding complete; live cluster smoke **blocked** (training container not yet built).
**Ticket:** T27
**Config:** `configs/model/qlora_smoke_v1.json`
**Core module:** `src/ambiguity_manager/model/qlora_smoke.py`

## Purpose

This is a *technical* smoke of the QLoRA adaptation-training mechanics, not a
training run and not a model-quality result. It exists solely to prove, on a
tiny (32-64 record) deterministic `source_train` subset, that:

- the frozen base checkpoint referenced by `selected_base_model` never
  changes during training;
- a trainable LoRA adapter attaches to that frozen base and does change;
- the adapter is saved to a location physically separate from any base
  snapshot, never merged into it;
- reloading the adapter validates the exact base identity it was trained
  against, and rejects a mismatched base;
- a resumed run picks up training state (step count) consistently with what
  was checkpointed;
- evidence (`qlora_smoke_result.json`, `adapter_identity.json`,
  `loss_mask_summary.json`, `run_manifest.json`) is always finalised, on
  both a successful and a failed run;
- no secret-shaped value (tokens, keys, passwords) is ever persisted into
  that evidence.

## Non-claims

This smoke is **never**:

- an official training run — every result payload is forced to carry
  `technical_smoke_only: true`, `selected_adapter: false`, and
  `valid_for_official_use: false` (`assert_training_run_not_official`);
- a route to `selected_adapter` — a smoke adapter's identity cannot be
  registered as `selected_adapter` under any circumstance
  (`assert_cannot_register_smoke_adapter_as_selected`);
- a substitute for real training-data scale, hyperparameter search, or
  held-out/manual evaluation. `max_steps` is deliberately far below anything
  used for a real run (see `configs/model/qlora_smoke_v1.json#training`);
- a change to the pinned vLLM inference container. The (planned) training
  container is a separate artefact; see "Container status" below.

## Hard requirements enforced

- `require_selected_base_model()` raises until Phase D populates
  `selected_base_model` in `configs/model/selected_identities_v1.json`. This
  module never invents, guesses, or defaults to an arbitrary base model.
- `reject_arbitrary_base_model()` only accepts a candidate identity that is
  byte-identical to the frozen `selected_base_model` **and** corresponds to
  an allowlisted entry in `configs/model/base_model_candidates_v1.json`.
- The smoke data subset (`data/development/qlora_smoke_v1/`) is built only
  from `source_train`; `source_dev`, `source_holdout`, the model-selection
  bake-off set, T13 calibration, the future manual namespace, and protected
  data are all structurally excluded (see
  `src/ambiguity_manager/model/qlora_smoke_data.py`).
- Training targets are packaged per `configs/data/training_target_policy_v1.json`
  strategy D: every field group carries its own per-record loss weight, and
  an unavailable/ineligible field group is masked (`loss_weight: 0.0`), never
  rewritten as a fabricated negative label
  (`assert_never_fabricates_negative_label`).

## Local vs. cluster execution

Locally (CPU-only, no `torch`/`transformers`/`peft`/`bitsandbytes`/`accelerate`
installed), `run_smoke_training()` falls back to
`MockQloraTrainingHarness`: a tiny deterministic stand-in using plain Python
floats that proves the *mechanical contract* above without any real tensors
or model weights. This is what `tests/test_t27_qlora_smoke.py` exercises;
it never loads a real model locally.

On the cluster, once the training container's dependencies are importable
(`check_qlora_provider_available()` reports `available=True`), the same
entry point takes the real path: 4-bit quantised load of the frozen base,
LoRA attach, one or more real forward/backward/optimiser steps, real
checkpoint save/reload, resume, an inference smoke comparing base-only vs.
base+adapter generations, and a best-effort structured-output parse check
(`run_real_qlora_smoke`, `run_real_inference_and_diff_smoke`).

## Container status

**Blocked.** `configs/environments/t12_cluster_training.json` documents
pinned target versions (Python, PyTorch/CUDA, Transformers, PEFT,
bitsandbytes, Accelerate) and points at
`configs/environments/t12_training_container.def`, an Apptainer recipe that
has **not been built into a live `.sif`** in this session
(`container_recipe.status: "recipe_only_not_built"`). The `qlora_smoke`
cluster job profile (`configs/cluster/t12_job_profiles.json#profiles.qlora_smoke`)
is wired to use a separate training container path
(`container_sif_default_relpath: "containers/t12-training-v1.sif"`) rather
than defaulting to the pinned inference SIF
(`vllm-openai-v0.20.1.sif`), so a live smoke run cannot accidentally reuse,
rebuild, or overwrite the inference container — but it also cannot run at
all until that training `.sif` is actually built and uploaded to the
cluster.

Until that build happens, and until Phase D populates `selected_base_model`,
the live cluster smoke (`python scripts/t12_cluster_job.py --run qlora_smoke
--poll --pull`) remains blocked. Everything upstream of that (data subset,
target packaging, config, mock-contract proof, operator profile, scripts)
is in place and tested so the live run is a matter of building the
container and running Phase D, not further design work.

## Files

| Component | Path |
|---|---|
| Smoke data builder | `src/ambiguity_manager/model/qlora_smoke_data.py`, `scripts/build_qlora_smoke_data.py` |
| Data subset output | `data/development/qlora_smoke_v1/` |
| Training-target packaging | `src/ambiguity_manager/model/training_target_packaging.py` |
| Smoke config | `configs/model/qlora_smoke_v1.json` |
| Training environment | `configs/environments/t12_cluster_training.json`, `configs/environments/t12_training_container.def` |
| Core module | `src/ambiguity_manager/model/qlora_smoke.py` |
| Cluster entry script | `scripts/t12_qlora_smoke.py` |
| Operator profile | `configs/cluster/t12_job_profiles.json#profiles.qlora_smoke` |
| Tests | `tests/test_t27_qlora_smoke.py` |
