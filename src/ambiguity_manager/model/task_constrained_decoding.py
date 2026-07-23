"""T27C constrained task-specific JSON decoding (HF Transformers compatible).

Pinned library: lm-format-enforcer.
No unconstrained fallback is permitted when constraints cannot initialise.
Heavy imports are lazy so CPU-only modules remain import-isolated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.paths import ProjectPaths

CONSTRAINT_CONFIG_REL = "configs/model/t27c_constrained_decoding_v1.json"
PINNED_LIBRARY = "lm-format-enforcer"
PINNED_VERSION = "0.10.12"


class ConstrainedDecodingError(RuntimeError):
    """Raised when task constraints cannot be initialised or applied."""


@dataclass(frozen=True)
class ConstraintIdentity:
    library: str
    version: str
    integration_point: str
    unconstrained_fallback_permitted: bool
    schema_hash: str
    task_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "library": self.library,
            "version": self.version,
            "integration_point": self.integration_point,
            "unconstrained_fallback_permitted": self.unconstrained_fallback_permitted,
            "schema_hash": self.schema_hash,
            "task_id": self.task_id,
        }


def load_constraint_config(root: Path | None = None) -> dict[str, Any]:
    base = (root or ProjectPaths.from_repo_root().root).resolve()
    path = base / CONSTRAINT_CONFIG_REL
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("library") != PINNED_LIBRARY:
        raise ConstrainedDecodingError("constraint library mismatch")
    if payload.get("version") != PINNED_VERSION:
        raise ConstrainedDecodingError("constraint version mismatch")
    if payload.get("unconstrained_fallback_permitted") is not False:
        raise ConstrainedDecodingError("unconstrained fallback must be false")
    return payload


def constraint_config_hash(root: Path | None = None) -> str:
    return sha256_hex(canonical_json_bytes(load_constraint_config(root)))


def build_constraint_identity(
    *,
    task_id: str,
    json_schema: Mapping[str, Any],
) -> ConstraintIdentity:
    return ConstraintIdentity(
        library=PINNED_LIBRARY,
        version=PINNED_VERSION,
        integration_point="transformers.LogitsProcessorList + JsonSchemaParser",
        unconstrained_fallback_permitted=False,
        schema_hash=sha256_hex(canonical_json_bytes(dict(json_schema))),
        task_id=task_id,
    )


def compile_task_constraint(json_schema: Mapping[str, Any]) -> Any:
    """Compile a task JSON schema into an lm-format-enforcer parser.

    Raises ConstrainedDecodingError on failure. Never falls back to unconstrained.
    """
    try:
        from lmformatenforcer import JsonSchemaParser
    except ImportError as exc:
        raise ConstrainedDecodingError(
            "lm-format-enforcer_not_available:cannot_initialise_constraints"
        ) from exc
    try:
        return JsonSchemaParser(dict(json_schema))
    except Exception as exc:  # noqa: BLE001
        raise ConstrainedDecodingError(
            f"constraint_compile_failed:{exc}"
        ) from exc


def build_transformers_logits_processor(
    tokenizer: Any,
    json_schema: Mapping[str, Any],
) -> Any:
    """Build an HF LogitsProcessor that enforces the task JSON schema."""
    try:
        from lmformatenforcer.integrations.transformers import (
            build_transformers_prefix_allowed_tokens_fn,
        )
        from lmformatenforcer import JsonSchemaParser
    except ImportError as exc:
        raise ConstrainedDecodingError(
            "lm-format-enforcer_transformers_integration_unavailable"
        ) from exc

    try:
        parser = JsonSchemaParser(dict(json_schema))
        prefix_fn = build_transformers_prefix_allowed_tokens_fn(tokenizer, parser)
    except Exception as exc:  # noqa: BLE001
        raise ConstrainedDecodingError(
            f"constraint_initialisation_failed:{exc}"
        ) from exc

    class _PrefixAllowedTokensProcessor:
        """Minimal LogitsProcessor wrapper around prefix-allowed tokens fn."""

        def __init__(self, allowed_fn):  # noqa: ANN001
            self._allowed_fn = allowed_fn

        def __call__(self, input_ids, scores):  # noqa: ANN001
            import torch

            batch = input_ids.shape[0]
            for i in range(batch):
                allowed = self._allowed_fn(i, input_ids[i])
                if allowed is None:
                    continue
                mask = torch.full_like(scores[i], float("-inf"))
                # allowed may be a list/set of token ids
                idx = list(allowed)
                if idx:
                    mask[idx] = 0.0
                    scores[i] = scores[i] + mask
            return scores

    return _PrefixAllowedTokensProcessor(prefix_fn)


def generate_with_task_constraint(
    *,
    model: Any,
    tokenizer: Any,
    prompt: str,
    json_schema: Mapping[str, Any],
    max_new_tokens: int,
    generation_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run constrained generation. Fails closed if constraints cannot init."""
    import torch

    processor = build_transformers_logits_processor(tokenizer, json_schema)
    encoded = tokenizer(prompt, return_tensors="pt")
    input_ids = encoded["input_ids"].to(model.device)
    attention_mask = encoded.get("attention_mask")
    if attention_mask is not None:
        attention_mask = attention_mask.to(model.device)

    gen_kwargs: dict[str, Any] = {
        "max_new_tokens": int(max_new_tokens),
        "do_sample": bool((generation_config or {}).get("do_sample", False)),
        "logits_processor": [processor],
    }
    if attention_mask is not None:
        gen_kwargs["attention_mask"] = attention_mask
    temperature = (generation_config or {}).get("temperature")
    if temperature is not None and gen_kwargs["do_sample"]:
        gen_kwargs["temperature"] = float(temperature)

    with torch.no_grad():
        output_ids = model.generate(input_ids, **gen_kwargs)
    continuation = output_ids[0, input_ids.shape[-1] :]
    text = tokenizer.decode(continuation, skip_special_tokens=True)
    return {
        "constraint_initialised": True,
        "raw_text": text,
        "transport_status": "constrained_generated",
        "unconstrained_fallback": False,
    }
