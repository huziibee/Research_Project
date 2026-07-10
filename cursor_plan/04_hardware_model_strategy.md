# 04 — Local Open-Source Model Strategy for Laptop RTX 3070 / 16GB RAM

This document is reference context for model tickets.

## Hardware caution

Do not confuse system RAM with GPU VRAM.

The laptop has 16GB system RAM, but the RTX 3070 laptop GPU may have much less VRAM. Cursor/code must verify with:

```bash
nvidia-smi
```

No model size may be assumed before this check.

## Recommended model stages

### Stage A — No local model dependency

Start with the project's schema, converters, evaluator, and baselines. These do not require a local LLM.

### Stage B — Prompted JSON baseline

Use any available LLM provider or local inference endpoint behind a small interface. The project should not hard-code one provider.

### Stage C — Local text LLM smoke test

Start with a small instruct model first, ideally quantized.

Candidate classes:

- 1B–3B instruct text model for JSON output smoke tests.
- 4B quantized model only if VRAM allows.
- 7B quantized model only if smoke tests prove stable.

### Stage D — LVLM only if truly needed

VAGUE may require visual context. Prefer text scene captions first. Do not fine-tune an LVLM unless explicitly approved.

### Stage E — QLoRA / adapter smoke test

Fine-tuning must start with 20–50 examples and one epoch or fewer. The goal is to prove the training loop works, not to claim final performance.

## Model abstraction rule

Implement a model adapter interface:

```text
manager calls ModelClient.generate_json(prompt, schema)
```

Do not scatter provider-specific calls across the codebase.

## Primary experimental model decision

The guaranteed primary experiment is a structured, schema-constrained prompted manager plus deterministic/rule-assisted routing components. Fine-tuning is an additional experimental condition, not a prerequisite for completing the core study. The final report must state exactly which conditions were actually run.

If fine-tuning is executed, compare it against the frozen prompted manager and all required baselines on the same protected test set. Do not redefine the proposed method after inspecting test performance.

## Repeatability

Use deterministic decoding for the primary comparison where supported. For stochastic conditions, use a predefined seed list and report mean, standard deviation, minimum, and maximum over repeated runs.
