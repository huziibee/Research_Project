# Mistral Stage-1 Empty-Result Diagnosis

**Date:** 2026-07-22  
**Run ID:** `t12-mc-transport-20260722T203945Z-da7e69e`  
**Slurm job:** `4364`  
**Candidate:** `mistral_small_24b_2501`  
**Node:** `mscluster111`  
**sacct:** `COMPLETED` / `ExitCode=0:0` / `Elapsed=00:05:15`

## Classification

**evidence-finalisation failure**

Secondary observation (not the empty-result root cause): `#SBATCH --output/--error` used unexpanded `${T12_CLUSTER_ROOT:-$HOME/t12-hpc}`, so Slurm wrote logs under a literal path inside the prep directory.

## Evidence inspected

| Artefact | Location |
|---|---|
| Local operator state | `outputs/t12_cluster_jobs/state.json` (job 4364) |
| Submission sbatch | `outputs/t12_cluster_jobs/t12-mc-transport-20260722T203945Z-da7e69e/submit.sbatch` |
| Remote prep | `$HOME/t12-hpc/runs/model-candidate-transport-smoke/.prep-t12-mc-transport-20260722T203945Z-da7e69e` |
| Remote result | `$HOME/t12-hpc/runs/model-candidate-transport-smoke/t12-mc-transport-20260722T203945Z-da7e69e` (**empty**) |
| Stdout/stderr | prep literal dir `.../${T12_CLUSTER_ROOT:-$HOME/t12-hpc}/logs/t12-mc-transport-4364.{out,err}` |

## Root cause

1. Snapshot resolved; tokenizer/vLLM engine started; model loaded (~43.91 GiB).
2. Structured generations ran for the four Stage-1 records (multiple repair attempts visible in stdout).
3. At least one accepted canonical payload carried `speech_act: "request"`.
4. JSON Schema permits any string for `speech_act`, so the generation pipeline accepted the payload.
5. `_analysis_output_row` → `StructuredAnalysis.from_dict` raised `SystemsContractError: invalid speech_act 'request'` because `INTENT_LABELS` does not include `"request"`.
6. The exception aborted `run_transport_smoke` **before** any evidence JSON/JSONL was written, leaving an empty result directory that the operator then pulled.

Direct traceback (stdout):

```text
File ".../bakeoff_provider.py", line 774, in _analysis_output_row
  analysis = canonical_to_structured_analysis(...)
File ".../systems/contracts.py", line 304, in from_dict
  raise SystemsContractError(f"invalid speech_act {speech_act!r}")
ambiguity_manager.systems.errors.SystemsContractError: invalid speech_act 'request'
```

## Why Qwen / Phi-4 were not emptied

Those jobs completed evidence finalisation successfully. The SBATCH log-path defect misplaced their logs the same way, but did not prevent result packaging. The empty-result crash required an accepted payload whose `speech_act` is outside `INTENT_LABELS`.

## Rerun justification

Permitted corrections applied:

- candidate-independent semantic validation: reject non-`INTENT_LABELS` `speech_act` values during payload validation (repairable schema failure);
- evidence-finalisation resilience: conversion failures downgrade acceptance instead of aborting the batch;
- generic path expansion: `#SBATCH --output/--error` now use absolute resolved log paths.

Rerun scope: **Mistral only**, new unique run ID. Preserve job-4364 evidence. Do not erase Qwen/Phi-4 Stage-1 packages. Do not retune prompts or weaken safety.

## Non-claims

- This does not convert Mistral into a zero-shot pass.
- This does not set `selected_base_model`, `selected_adapter`, or `selected_model_strategy`.
- Zero-shot Stage-1 failures remain preserved.
