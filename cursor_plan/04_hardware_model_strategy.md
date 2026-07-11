# 04 — Cluster and Local Model Strategy

This project is text-first. LVLM/raw-image work is excluded.

T12 has two model stacks with distinct authority:

1. **Authoritative cluster stack** — active T12 acceptance path (Stages A–I).
2. **Historical local stack** — preserved WSL/RTX 3070 evidence only; not authoritative after Stage A ADR acceptance.

## Authoritative cluster stack

```text
research code (local dev machine)
  -> Slurm submission / monitoring
  -> Wits HPC biggpu partition (exclusive node allocation)
  -> Apptainer vLLM container (vllm-openai-v0.20.1.sif)
  -> Qwen/Qwen3-8B @ b968826d9c46dd6066d109eabc6255188de91218
  -> direct Python vLLM batch inference (primary)
  -> optional OpenAI-compatible vLLM server (interactive dev only)
  -> raw output
  -> schema-v2 deterministic validator (Python authoritative)
  -> canonical prediction
  -> result publication (private GitHub results repo + release assets)
```

Cluster responsibilities:

- authoritative model weight storage (shared cluster cache);
- inference environment (Apptainer SIF, SHA-pinned);
- separate cluster training environment (Stage F; not the inference SIF);
- GPU execution, benchmarking, batch inference;
- packaging and external archival.

Local computer responsibilities:

- repository development and Cursor code review;
- SSH client tooling and Slurm job submission (future stages);
- pulling small manifests and summaries from the cluster.

Cluster-validation model (provisional, Stages A–H):

- `Qwen/Qwen3-8B`
- revision `b968826d9c46dd6066d109eabc6255188de91218`
- `candidate_status: provisionally_selected_for_cluster_validation`
- `model_licence_register.selected_model: null` until Stage I

Execution defaults:

- one persistent vLLM engine per GPU per job step;
- independent model replica per GPU node;
- data parallelism by default (not tensor parallelism);
- structured JSON decoding for schema-v2 outputs.

## Historical / non-authoritative local stack

The following local stack was implemented and preserved on `archive/t12-local-wsl-slice4`. It is **historical evidence only**:

```text
Windows host
  -> WSL2 Ubuntu
  -> RTX 3070 Laptop GPU
  -> Hugging Face Transformers + bitsandbytes NF4
  -> Qwen2.5-1.5B-Instruct (local working candidate)
  -> .venv-t12-inference / .venv-t12-training
  -> local Hugging Face cache
```

Historical facts recorded:

- RTX 3070 VRAM, driver, and WSL CUDA visibility were measured and manifest-recorded.
- Ungated model candidates and licences were verified on main through `b4865b3`.
- Local synthetic evaluation produced **0/10 schema-valid outputs**, motivating structured decoding and cluster migration.
- This stack does **not** determine Qwen3-8B cluster acceptance.

Do not infer cluster VRAM or throughput from the local RTX 3070 measurements.

## Planned final local state (after Stage I cleanup gate)

| Asset | Disposition |
|---|---|
| Repository | retained |
| Source code | retained |
| Tests and manifests | retained |
| Historical evidence | retained under `configs/model/evidence/historical/` |
| Git history | retained |
| Qwen2.5 local model weights | **removed** after cleanup gate (separate gated task) |
| `.venv-t12-inference` / `.venv-t12-training` | **removed** after cleanup gate |
| WSL installation | **not** automatically removed |

Local model deletion is **prohibited** during Stages A–H. Stage I documents eligibility only; deletion requires a separate human-gated cleanup task.

## Selection requirements (cluster path)

The cluster-validation model must:

- run on Wits HPC biggpu nodes inside the pinned vLLM SIF;
- support the required context and structured output workflow;
- have a licence compatible with academic inference and adapter fine-tuning;
- have an exact checkpoint available in the cluster shared cache;
- produce reproducible schema-constrained outputs at an acceptable invalid-output rate on synthetic fixtures before any research-pool use.

Final selection occurs in Stage I only after Stages C–H acceptance gates pass.

## Fair-comparison design

The direct LLM baseline and proposed manager share the same base model and revision.

- `direct_base_llm`: base model without the supervised adapter, direct structured prediction.
- `full_finetuned_type_risk_manager`: same base model plus the required adapter and deterministic router.
- T33 adds a 2x2 architecture/adaptation ablation so architecture gains are not confused with fine-tuning gains.

Hold constant quantisation, context/output limits, and decoding wherever the condition permits.

## Mandatory training strategy

- **Inference:** cluster vLLM batch backend inside pinned Apptainer SIF (primary); optional OpenAI-compatible server for interactive development.
- **Training:** separate cluster training environment (Stage F); not the inference SIF.
- T27 must prove the complete training loop on a small train/dev subset.
- T28 must perform full supervised train/dev-only adaptation and produce the adapter used by the proposed manager.
- Protected test data is first accessed in T30 after T29 freeze.
- The exact base checkpoint used for training must load the adapter.
- If mandatory fine-tuning cannot be completed, return `BLOCKED`; do not silently replace the proposed method with prompting.

## Training target

Fine-tune the model to emit schema-constrained structured analysis:

- intent/speech act and CPC frame;
- candidate interpretations and evidence;
- ambiguity labels and unresolved slots;
- risk/capability labels;
- context-sampling-compatible structured fields;
- proposed route/sequence and response targets.

The deterministic routing policy remains the final authority for the full manager route.

## Resource discipline

Cluster jobs use exclusive node allocation on biggpu. Measure cold/warm load, throughput, and peak VRAM on cluster hardware. Do not present 25,000-record throughput estimates as verified until Stage G benchmark evidence exists.

Historical local resource discipline (RTX 3070, NF4, small batches) remains documented on the archive branch for comparison only.
