# Historical WSL / RTX 3070 model evidence

This directory holds **historical evidence** from the superseded local Windows/WSL T12 implementation. It is **not** the active cluster acceptance evidence path.

## Why this evidence is preserved

The local implementation on branch `archive/t12-local-wsl-slice4` (commit: `chore(t12): preserve local WSL model evaluation before cluster redesign`) documented:

- RTX 3070 hardware measurements;
- WSL2 CUDA environment verification;
- ungated model candidate and licence verification;
- Qwen2.5-1.5B-Instruct local inference attempts;
- synthetic evaluation outcomes including **0/10 schema-valid outputs**.

These facts motivated the cluster redesign: structured JSON decoding, Qwen3-8B cluster validation, and vLLM batch execution. Erasing this evidence would lose the rationale for architectural change.

## What this evidence is not

- **Not** Qwen3-8B cluster acceptance evidence.
- **Not** authoritative for current T12 runtime decisions.
- **Not** a substitute for Stages C–I cluster GPU evidence.

Qwen2.5-1.5B results recorded here are **historical only**. They must not be interpreted as evidence that Qwen/Qwen3-8B will or will not pass cluster gates.

## Evidence relocation (Stage B)

Actual file movement from active paths to `configs/model/evidence/historical/` occurs in **Stage B** of `cursor_plan/tickets/T12_cluster_model_stack_setup.md`. Stage A creates this README and the policy contract only.

Expected relocated artefacts (Stage B):

- `configs/environments/historical/t12_inference_environment.json`
- `configs/environments/historical/t12_training_environment.json`
- `configs/model/evidence/historical/t12_hardware_manifest.json`
- `configs/model/evidence/historical/t12_environment_compatibility.json`
- `configs/model/evidence/historical/t12_model_candidates.json`
- `configs/model/evidence/historical/t12_checkpoint_download.json`
- `requirements/historical/t12-wsl2/*`
- `scripts/historical/t12-wsl2/*`

## Model weights

Model weight files are **never tracked in Git**. Local Qwen2.5-1.5B weights remain on disk in the WSL Hugging Face cache until the Stage I cleanup gate.

After Stage I acceptance:

- local T12 model weights become **eligible for deletion**;
- deletion is performed only through a **separate gated cleanup task**;
- this README and relocated manifests remain in the repository permanently.

## Cross-references

- ADR: `docs/decisions/ADR_T12_cluster_inference_architecture.md`
- Active ticket: `cursor_plan/tickets/T12_cluster_model_stack_setup.md`
- Superseded ticket: `cursor_plan/tickets/T12_local_text_model_and_training_stack_setup.md`
- Archive branch: `archive/t12-local-wsl-slice4`
