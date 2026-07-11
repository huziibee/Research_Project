# 04 — Local Text-LLM and Mandatory Fine-Tuning Strategy

This project is local-only and text-first. LVLM/raw-image work is excluded.

## Hardware rule

Do not infer VRAM from 16 GB system RAM. T12 must record actual RTX 3070 VRAM, free memory, driver, CUDA visibility, operating system, and training compatibility before selecting a model.

## Local architecture

```text
research code
  -> ModelClient.generate_json(prompt, schema)
  -> local inference runtime/API
  -> local text model
  -> raw output
  -> parser/schema validator
  -> canonical prediction
```

Provider/runtime-specific code remains inside adapters.

## Selection requirements

The chosen base model must:

- run reliably on the measured RTX 3070 for inference;
- support the required context and structured output workflow;
- have a licence compatible with local academic inference and adapter fine-tuning;
- have an exact checkpoint available to the training stack;
- be small enough for a mandatory LoRA/QLoRA training path on the available hardware;
- produce reproducible schema-constrained outputs at an acceptable invalid-output rate.

T12 must test current candidates from smaller to larger quantised variants using non-test examples. Record rejected candidates and evidence.

## Fair-comparison design

The direct LLM baseline and proposed manager share the same base model and revision.

- `direct_base_llm`: base model without the supervised adapter, direct structured prediction.
- `full_finetuned_type_risk_manager`: same base model plus the required adapter and deterministic router.
- T33 adds a 2x2 architecture/adaptation ablation so architecture gains are not confused with fine-tuning gains.

Hold constant quantisation, context/output limits, and decoding wherever the condition permits.

## Mandatory training strategy

- Inference: approved local runtime such as Ollama, llama.cpp, or an equivalent adapter-backed server.
- Training: Hugging Face Transformers + PEFT/TRL/bitsandbytes, or a verified equivalent local LoRA/QLoRA stack.
- T27 must prove the complete training loop on a small train/dev subset.
- T28 must perform full supervised train/dev-only adaptation and produce the adapter used by the proposed manager.
- Protected test data is first accessed in T30 after T29 freeze.
- The exact base checkpoint used for training must load the adapter.
- If local mandatory fine-tuning cannot be completed, return `BLOCKED`; do not silently replace the proposed method with prompting.

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

Start with short sequences, small batches, gradient accumulation, gradient checkpointing, 4-bit base weights where supported, and LoRA adapters. Measure peak VRAM and runtime; do not claim feasibility until the smoke training succeeds.
