"""Shared Hugging Face load, generate, and cleanup helpers (optional ML imports)."""

from __future__ import annotations

import gc
import time
from typing import Any

from ambiguity_manager.model.checkpoint_load import (
    AUTHORIZED_REPOSITORY_ID,
    AUTHORIZED_REVISION_SHA,
    AUTHORIZED_TOKENIZER_REVISION_SHA,
    LOADED_QUANTIZED_STORAGE_NUMEL_SOURCE,
    QuantisationConfig,
    build_architectural_parameter_evidence,
    build_cleanup_evidence,
    build_in_process_cleanup_evidence,
    build_quantisation_config,
    gpu_free_vram_mib,
    load_verified_config_dict,
)
from ambiguity_manager.model.context_budget import (
    DEFAULT_SAFETY_MARGIN,
    compute_effective_max_new_tokens,
)
from ambiguity_manager.model.errors import ModelClientError
from ambiguity_manager.model.protocol import ModelRuntimeSpec, monotonic_ms


def torch_bf16_supported() -> bool:
    import torch

    if not torch.cuda.is_available():
        return False
    return bool(getattr(torch.cuda, "is_bf16_supported", lambda: False)())


def build_bnb_config(quant: QuantisationConfig) -> Any:
    import torch
    from transformers import BitsAndBytesConfig

    dtype_name = quant.bnb_4bit_compute_dtype
    compute_dtype = getattr(torch, dtype_name)
    return BitsAndBytesConfig(
        load_in_4bit=quant.load_in_4bit,
        bnb_4bit_quant_type=quant.bnb_4bit_quant_type,
        bnb_4bit_use_double_quant=quant.bnb_4bit_use_double_quant,
        bnb_4bit_compute_dtype=compute_dtype,
    )


def load_tokenizer(*, local_files_only: bool = True) -> Any:
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(
        AUTHORIZED_REPOSITORY_ID,
        revision=AUTHORIZED_REVISION_SHA,
        local_files_only=local_files_only,
        trust_remote_code=False,
    )


def load_model(
    *,
    quant: QuantisationConfig,
    local_files_only: bool = True,
) -> Any:
    import torch
    from transformers import AutoModelForCausalLM

    bnb_config = build_bnb_config(quant)
    return AutoModelForCausalLM.from_pretrained(
        AUTHORIZED_REPOSITORY_ID,
        revision=AUTHORIZED_REVISION_SHA,
        quantization_config=bnb_config,
        device_map=quant.device_map,
        trust_remote_code=False,
        local_files_only=local_files_only,
        low_cpu_mem_usage=quant.low_cpu_mem_usage,
        attn_implementation=quant.attn_implementation,
    )


def collect_identity_evidence(
    model: Any,
    tokenizer: Any,
    *,
    config_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import torch

    config = model.config
    loaded_quantized_storage_numel = sum(p.numel() for p in model.parameters())
    loaded_in_4bit = any(getattr(p, "quant_state", None) is not None for p in model.parameters())
    if not loaded_in_4bit:
        loaded_in_4bit = getattr(model, "is_loaded_in_4bit", False)

    device_placement = "unknown"
    try:
        device_placement = str(next(model.parameters()).device)
    except StopIteration:
        pass

    compute_dtype = "unknown"
    if torch.cuda.is_available():
        compute_dtype = str(torch.get_default_dtype())

    memory_footprint = None
    if torch.cuda.is_available():
        memory_footprint = int(torch.cuda.max_memory_allocated())

    identity: dict[str, Any] = {
        "model_type": getattr(config, "model_type", None),
        "architectures": list(getattr(config, "architectures", []) or []),
        "vocab_size": getattr(config, "vocab_size", None),
        "context_limit": getattr(config, "max_position_embeddings", None),
        "tokenizer_class": type(tokenizer).__name__,
        "tokenizer_vocab_size": len(tokenizer),
        "bos_token_id": tokenizer.bos_token_id,
        "eos_token_id": tokenizer.eos_token_id,
        "pad_token_id": tokenizer.pad_token_id,
        "loaded_in_4bit": bool(loaded_in_4bit),
        "compute_dtype": compute_dtype,
        "cuda_device_placement": device_placement,
        "immutable_revision_sha": AUTHORIZED_REVISION_SHA,
        "tokenizer_revision_sha": AUTHORIZED_TOKENIZER_REVISION_SHA,
        "loaded_quantized_storage_numel": loaded_quantized_storage_numel,
        "loaded_quantized_storage_numel_source": LOADED_QUANTIZED_STORAGE_NUMEL_SOURCE,
        "loaded_model_memory_footprint_bytes": memory_footprint,
    }
    identity.update(build_architectural_parameter_evidence(config=config_dict))
    return identity


def verify_peft_architecture(model: Any) -> bool:
    """Inspect PEFT target-module mapping without attaching an adapter."""
    try:
        from peft.utils.constants import TRANSFORMERS_MODELS_TO_LORA_TARGET_MODULES_MAPPING
    except ImportError:
        return False

    model_type = getattr(model.config, "model_type", None)
    if not isinstance(model_type, str):
        return False
    target_modules = TRANSFORMERS_MODELS_TO_LORA_TARGET_MODULES_MAPPING.get(model_type)
    if not target_modules:
        return False

    module_names = {name for name, _ in model.named_modules()}
    for target in target_modules:
        if any(target in name for name in module_names):
            return True
    return False


def cleanup_model(
    model: Any | None,
    tokenizer: Any | None,
    *,
    baseline_free_vram_mib: float | None = None,
) -> dict[str, Any]:
    import torch

    references_released = False
    gc_collected = False
    cuda_cache_cleared = False

    try:
        del model
        del tokenizer
        references_released = True
    except Exception:  # noqa: BLE001
        pass

    gc_collected = bool(gc.collect())

    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            cuda_cache_cleared = True
        except Exception:  # noqa: BLE001
            pass

    in_process_free = gpu_free_vram_mib()
    in_process = build_in_process_cleanup_evidence(
        references_released=references_released,
        gc_collect_completed=gc_collected,
        cuda_empty_cache_completed=cuda_cache_cleared,
        in_process_post_cleanup_free_vram_mib=in_process_free,
        baseline_free_vram_mib=baseline_free_vram_mib,
    )
    return in_process


def peak_vram_mib() -> float | None:
    import torch

    if not torch.cuda.is_available():
        return None
    return round(torch.cuda.max_memory_allocated() / (1024 * 1024), 3)


def generate_raw_output(
    *,
    model: Any,
    tokenizer: Any,
    messages: list[dict[str, str]],
    seed: int,
    do_sample: bool,
    top_p: float | None,
    requested_max_new_tokens: int,
    model_context_limit: int,
    safety_margin: int = DEFAULT_SAFETY_MARGIN,
) -> dict[str, Any]:
    import torch

    if hasattr(tokenizer, "apply_chat_template"):
        prompt_text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    else:
        parts = []
        for message in messages:
            parts.append(f"{message['role']}: {message['content']}")
        prompt_text = "\n".join(parts) + "\nassistant:"

    prompt_tokens = len(tokenizer.encode(prompt_text, add_special_tokens=False))
    effective_max = compute_effective_max_new_tokens(
        requested_max_new_tokens=requested_max_new_tokens,
        model_context_limit=model_context_limit,
        prompt_token_count=prompt_tokens,
        safety_margin=safety_margin,
    )

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    gen_kwargs: dict[str, Any] = {
        "max_new_tokens": effective_max,
        "do_sample": do_sample,
        "use_cache": True,
        "pad_token_id": tokenizer.pad_token_id or tokenizer.eos_token_id,
    }
    if do_sample and top_p is not None:
        gen_kwargs["top_p"] = top_p

    inputs = tokenizer(prompt_text, return_tensors="pt")
    device = next(model.parameters()).device
    inputs = {key: value.to(device) for key, value in inputs.items()}

    start = monotonic_ms()
    with torch.inference_mode():
        output_ids = model.generate(**inputs, **gen_kwargs)
    latency_ms = monotonic_ms() - start

    input_len = inputs["input_ids"].shape[-1]
    completion_ids = output_ids[0, input_len:]
    raw_output = tokenizer.decode(completion_ids, skip_special_tokens=True)

    return {
        "raw_output": raw_output,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": len(completion_ids),
        "effective_max_new_tokens": effective_max,
        "latency_ms": latency_ms,
        "peak_vram_mib": peak_vram_mib(),
    }


def generation_worker(payload: dict[str, Any]) -> dict[str, Any]:
    runtime = ModelRuntimeSpec(**payload["runtime"])
    request = payload["request"]
    messages = request["messages"]
    seed = int(request.get("seed", 0))
    do_sample = bool(request.get("do_sample", False))
    top_p = request.get("top_p")
    requested_max_new_tokens = int(request["requested_max_new_tokens"])
    model_context_limit = int(payload["model_context_limit"])

    bf16 = torch_bf16_supported()
    quant = build_quantisation_config(bf16_supported=bf16)
    if runtime.quantisation != "nf4_4bit":
        raise ModelClientError("quantisation must be nf4_4bit")

    import torch

    torch.cuda.reset_peak_memory_stats()
    tokenizer = load_tokenizer(local_files_only=True)
    model = load_model(quant=quant, local_files_only=True)

    try:
        result = generate_raw_output(
            model=model,
            tokenizer=tokenizer,
            messages=messages,
            seed=seed,
            do_sample=do_sample,
            top_p=top_p if do_sample else None,
            requested_max_new_tokens=requested_max_new_tokens,
            model_context_limit=model_context_limit,
        )
        result["identity"] = collect_identity_evidence(
            model,
            tokenizer,
            config_dict=model.config.to_dict() if hasattr(model.config, "to_dict") else None,
        )
        result["quantisation"] = quant.as_dict()
        return result
    finally:
        cleanup_model(model, tokenizer)


def sleeping_worker(_payload: dict[str, Any]) -> dict[str, Any]:
    time.sleep(60)
    return {"raw_output": "should not arrive"}
