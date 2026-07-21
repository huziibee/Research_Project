# ADR: T12 Cluster Inference Architecture

**Status:** Accepted (Stage A)  
**Date:** 2026-07-11  
**Supersedes (as active runtime authority):** local Windows/WSL RTX 3070 design documented in `cursor_plan/tickets/T12_local_text_model_and_training_stack_setup.md`  
**Active execution contract:** `cursor_plan/tickets/T12_cluster_model_stack_setup.md`  
**Archive branch:** `archive/t12-local-wsl-slice4`  
**Forward-migration base:** `b4865b3a101c87b7b5fe468c12c40adead74068f`  
**Governance deviation:** `DEV-20260711-001` (historical preparatory authorisation; pending-ethics rationale closed by `DEV-20260721-001` / `ETHGOV-001`)
**Current T11 gate:** PASS — determination `not_required` (supervisor-only annotation)

## Context

T12 began as a local Windows/WSL RTX 3070 text-model and training-stack setup under `DEV-20260711-001`. That work produced hardware evidence, candidate licence verification, environment manifests, checkpoint download scaffolding, and a preserved local implementation on `archive/t12-local-wsl-slice4` (commit subject: `chore(t12): preserve local WSL model evaluation before cluster redesign`).

Local synthetic evaluation on Qwen2.5-1.5B-Instruct with Transformers and bitsandbytes NF4 produced **0/10 schema-valid outputs** after bounded attempts. This result is historical evidence only; it motivated structured JSON decoding and a larger cluster-validation model rather than further local stack investment.

The Wits HPC cluster provides authoritative GPU execution, shared model storage, Apptainer containers, and Slurm scheduling. The local RTX 3070 and WSL stack are no longer authoritative for T12 acceptance. They remain preserved source code and historical evidence until the Stage I cleanup gate.

T11 is **PASS** with determination `not_required` for supervisor-only annotation (`ETHGOV-001`). Historically, T11 was BLOCKED on a pending institutional ethics determination during early T12 preparatory work under `DEV-20260711-001`. No research-pool records, protected data, or T13/T14 collection is permitted during Stages A–H. External annotators remain forbidden without reassessment.

## Previous local Windows/WSL design

The superseded local design assigned authoritative runtime to:

- Windows host + WSL2 Ubuntu
- RTX 3070 Laptop GPU (8 GB VRAM class)
- Hugging Face Transformers + bitsandbytes NF4 quantisation
- Qwen2.5-1.5B-Instruct as the working local candidate
- Separate `.venv-t12-inference` and `.venv-t12-training` environments
- Local Hugging Face model cache under WSL

That design is preserved on `archive/t12-local-wsl-slice4` and must not be deleted during Stages A–H.

## Decision

Forward migrate T12 from committed pre-redesign HEAD `b4865b3a101c87b7b5fe468c12c40adead74068f` onto branch `feature/t12-cluster-redesign`. Do **not** reset to pre-T12 baseline `7706ee5`.

### Reason for not resetting to `7706ee5`

Resetting would discard committed T12 foundation work that remains valid and referenced:

- deterministic model foundation and hardware evidence (`c60f043`);
- WSL CUDA environment verification (`0e9402a`);
- ungated model candidate and licence verification (`812b1f3`, `8e2a47b`);
- controlled checkpoint download scaffold (`8e2a47b`, `b4865b3`).

The cluster redesign replaces the **runtime authority** and **acceptance path**, not the governance, schema-v2, or licence-verification history accumulated on main through `b4865b3`. Historical WSL implementation code lives on the archive branch and is referenced, not replayed, on the feature branch.

### Runtime authority split

**Local computer responsibilities:**

- repository development and code review;
- Cursor IDE workflow;
- SSH client tooling (future stages; not used in Stage A);
- Slurm job submission and monitoring (future stages);
- pulling small reports, manifests, and summaries from the cluster.

**Wits cluster responsibilities:**

- authoritative model weight storage;
- inference environment (Apptainer vLLM SIF);
- separate future adapter-feasibility / training environment;
- GPU execution, benchmarking, and batch inference;
- result packaging and publication to the dedicated results repository.

### Cluster-validation model identity

| Field | Value |
|---|---|
| Model ID | `Qwen/Qwen3-8B` |
| Immutable revision SHA | `b968826d9c46dd6066d109eabc6255188de91218` |
| Candidate status (Stages A–H) | `provisionally_selected_for_cluster_validation` |
| `model_licence_register.selected_model` | `null` (unchanged until Stage I) |

### Inference container identity

| Field | Value |
|---|---|
| Apptainer image | `vllm-openai-v0.20.1.sif` |
| Immutable SHA-256 | `d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1` |

### Execution architecture

- **Primary mode:** direct Python vLLM batch inference inside the Apptainer container on Slurm GPU jobs.
- **Secondary mode (optional):** OpenAI-compatible vLLM server for interactive development only; not the authoritative batch path.
- **Engine lifecycle:** one persistent vLLM engine per GPU for the duration of a job step.
- **Multi-node default:** independent model replica per GPU node with data parallelism; tensor parallelism is not the default.
- **Schema authority:** schema-v2 deterministic validation in Python remains authoritative over model output.
- **Policy boundary:** the model proposes structured analysis; the deterministic routing policy remains the final authority for manager route decisions.
- **Stack separation:** inference SIF and future training environment are separate; the inference container is not treated as the training stack.

### Governance boundary (synthetic-only during Stages A–H)

During Stages A–H:

- execution is synthetic-fixture and synthetic-corpus only;
- full research-pool execution is prohibited;
- optimiser steps equal zero except in Stage F feasibility probes explicitly scoped to adapter attach/save with zero research records;
- no protected data access;
- no T13 or T14 collection (technical/protocol gates unmet);
- T11 gate is PASS with determination `not_required`; external annotators remain forbidden;
- historical measurement artefacts that recorded `t11_status: BLOCKED` remain valid for their measurement time.

### Historical evidence preservation

- WSL/RTX 3070 evidence remains valid as **historical evidence only**.
- Evidence relocation to `configs/model/evidence/historical/` occurs in Stage B, not Stage A.
- Local model weights and T12-specific environments are **not** deleted until Stage I cleanup gate acceptance.
- Stage I documents eligibility for deletion; it does not perform automatic deletion.

### Intended final local state (after Stage I cleanup gate)

| Asset | Final state |
|---|---|
| Source code | preserved |
| Git history | preserved |
| Tests and manifests | preserved |
| Historical evidence | preserved under `configs/model/evidence/historical/` |
| Qwen2.5 local model weights | removed after cleanup gate |
| `.venv-t12-inference` / `.venv-t12-training` | removed after cleanup gate |
| WSL installation | not automatically removed |

### Result-publication architecture (planned; not yet operational)

- **Private dedicated GitHub results repository** for large run artefacts.
- **Small manifests and summaries** committed to the results repository.
- **Large output bundles** uploaded as GitHub release assets.
- **Dependent CPU finaliser** Slurm job using `afterany` dependency on GPU inference jobs.
- **Email notification** via Slurm `#SBATCH --mail-type`.
- **Optional WhatsApp notification** via workflow hook (credentials excluded from source).
- **Cluster copy retained** when remote publication fails; `EXTERNALLY_ARCHIVED` reached only when all expected remote assets and manifests are verified.

Required publication states (Stage H contract):

`INFERENCE_RUNNING`, `INFERENCE_PASS`, `INFERENCE_FAILED`, `VALIDATION_PASS`, `VALIDATION_FAILED`, `PACKAGING_PASS`, `PACKAGING_FAILED`, `PUBLICATION_PASS`, `PUBLICATION_FAILED`, `NOTIFICATION_PASS`, `NOTIFICATION_FAILED`, `EXTERNALLY_ARCHIVED`.

## Consequences

### Positive

- Authoritative GPU execution on cluster hardware suitable for Qwen3-8B.
- Structured JSON decoding path can be validated at scale before any research-pool use.
- Clear separation between historical local evidence and cluster acceptance evidence.
- Publication pipeline designed for reproducibility and external archival.

### Negative / risks

- Cluster dependency introduces scheduling latency and operational complexity.
- vLLM container and Qwen3-8B revision must remain pinned; drift breaks reproducibility.
- Publication pipeline is not yet operational; Stage H must prove end-to-end flow.
- Local WSL stack may be misread as current authority if archive/historical labelling is ignored.
- 25,000-record throughput estimates must not be presented as verified until Stage G evidence exists.

## Superseded documentation

| Document | Status |
|---|---|
| `cursor_plan/tickets/T12_local_text_model_and_training_stack_setup.md` | SUPERSEDED — historical reference only |
| Local-first sections of `cursor_plan/04_hardware_model_strategy.md` | Updated — cluster authoritative, local historical |

## Relationship to DEV-20260711-001

`DEV-20260711-001` historically authorised **T12 preparatory work** while T11 was BLOCKED on a pending ethics determination. That pending-ethics rationale is **closed / superseded** by `DEV-20260721-001` after `ETHGOV-001` recorded determination status `not_required` for supervisor-only annotation. Completed work under `DEV-20260711-001` remains valid. This ADR does not authorise external annotators, research-pool execution during Stages A–H, or T13/T14 collection before their technical gates.

## Explicit non-claims

This ADR does **not** claim:

- that the determination is an ethics approval, exemption, or waiver;
- Qwen3-8B is finally accepted as the project model;
- the cluster training environment exists or passed LoRA feasibility;
- the full schema-v2 bake-off passed on cluster hardware;
- the live D-Final smoke passed;
- the research pool was processed;
- publication is already operational;
- local model deletion has occurred;
- `model_licence_register.selected_model` has been set;
- T13/T14 have started.

Only Stage I may set `selected_model` after every acceptance gate passes.
