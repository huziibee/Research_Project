"""T27C constrained task-specific JSON decoding (HF Transformers compatible).

Pinned library: lm-format-enforcer==0.10.12.
No unconstrained fallback is permitted when constraints cannot initialise.

The stock ``lmformatenforcer.integrations.transformers`` module imports
``PreTrainedTokenizerBase`` from ``transformers.tokenization_utils``, which
fails on the cluster transformers build (job 7054:
``lm-format-enforcer_transformers_integration_unavailable``). This module
uses lm-format-enforcer *core* (``JsonSchemaParser`` / ``TokenEnforcer``) and
HF ``prefix_allowed_tokens_fn`` instead.
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.paths import ProjectPaths

CONSTRAINT_CONFIG_REL = "configs/model/t27c_constrained_decoding_v1.json"
PINNED_LIBRARY = "lm-format-enforcer"
PINNED_VERSION = "0.10.12"

# Process-local cache: building the token→str table over a 150k vocab is expensive.
_TOKENIZER_DATA_CACHE: dict[int, Any] = {}


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
        integration_point=(
            "transformers.prefix_allowed_tokens_fn + JsonSchemaParser "
            "(core TokenEnforcer; not stock integrations.transformers)"
        ),
        unconstrained_fallback_permitted=False,
        schema_hash=sha256_hex(canonical_json_bytes(dict(json_schema))),
        task_id=task_id,
    )


def compile_task_constraint(json_schema: Mapping[str, Any]) -> Any:
    """Compile a task JSON schema into an lm-format-enforcer parser."""
    try:
        from lmformatenforcer import JsonSchemaParser
    except ImportError as exc:
        raise ConstrainedDecodingError(
            "lm-format-enforcer_not_available:cannot_initialise_constraints"
        ) from exc
    try:
        return JsonSchemaParser(dict(json_schema))
    except Exception as exc:  # noqa: BLE001
        raise ConstrainedDecodingError(f"constraint_compile_failed:{exc}") from exc


def _build_token_enforcer_tokenizer_data(tokenizer: Any) -> Any:
    """Mirror lm-format-enforcer's tokenizer-data builder without the broken import."""
    from lmformatenforcer import TokenEnforcerTokenizerData

    cache_key = id(tokenizer)
    cached = _TOKENIZER_DATA_CACHE.get(cache_key)
    if cached is not None:
        return cached

    vocab_size = int(getattr(tokenizer, "vocab_size", 0) or len(tokenizer))
    # Prefer the full tokenizer length when it exceeds vocab_size (Qwen3: 151669 vs 151643).
    try:
        vocab_size = max(vocab_size, len(tokenizer))
    except Exception:  # noqa: BLE001
        pass

    token_0 = tokenizer.encode("0")[-1]
    special_ids = set(getattr(tokenizer, "all_special_ids", None) or [])
    regular_tokens: list[tuple[int, str, bool]] = []
    for token_idx in range(vocab_size):
        if token_idx in special_ids:
            continue
        decoded_after_0 = tokenizer.decode([token_0, token_idx])[1:]
        decoded_regular = tokenizer.decode([token_idx])
        is_word_start_token = len(decoded_after_0) > len(decoded_regular)
        regular_tokens.append((token_idx, decoded_after_0, is_word_start_token))

    def _decode(tokens: list[int]) -> str:
        return tokenizer.decode(tokens).rstrip("�")

    data = TokenEnforcerTokenizerData(
        regular_tokens,
        functools.partial(_decode),
        tokenizer.eos_token_id,
    )
    _TOKENIZER_DATA_CACHE[cache_key] = data
    return data


def build_prefix_allowed_tokens_fn(tokenizer: Any, json_schema: Mapping[str, Any]) -> Any:
    """Build HF ``prefix_allowed_tokens_fn`` for the given task schema."""
    try:
        from lmformatenforcer import JsonSchemaParser, TokenEnforcer
    except ImportError as exc:
        raise ConstrainedDecodingError(
            "lm-format-enforcer_not_available:cannot_initialise_constraints"
        ) from exc

    try:
        parser = JsonSchemaParser(dict(json_schema))
        tokenizer_data = _build_token_enforcer_tokenizer_data(tokenizer)
        token_enforcer = TokenEnforcer(tokenizer_data, parser)
    except ConstrainedDecodingError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ConstrainedDecodingError(
            f"constraint_initialisation_failed:{exc}"
        ) from exc

    def _prefix_allowed_tokens_fn(batch_id: int, sent: Any) -> list[int]:  # noqa: ARG001
        if hasattr(sent, "tolist"):
            token_sequence = sent.tolist()
        else:
            token_sequence = list(sent)
        return list(token_enforcer.get_allowed_tokens(token_sequence))

    return _prefix_allowed_tokens_fn


def build_transformers_logits_processor(
    tokenizer: Any,
    json_schema: Mapping[str, Any],
) -> Any:
    """Compatibility wrapper: returns a prefix-allowed-tokens callable.

    Historical name retained for tests; prefer
    :func:`build_prefix_allowed_tokens_fn` for new call sites.
    """
    return build_prefix_allowed_tokens_fn(tokenizer, json_schema)


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

    prefix_fn = build_prefix_allowed_tokens_fn(tokenizer, json_schema)
    encoded = tokenizer(prompt, return_tensors="pt")
    device = next(model.parameters()).device
    input_ids = encoded["input_ids"].to(device)
    attention_mask = encoded.get("attention_mask")
    if attention_mask is not None:
        attention_mask = attention_mask.to(device)

    gen_kwargs: dict[str, Any] = {
        "max_new_tokens": int(max_new_tokens),
        "do_sample": bool((generation_config or {}).get("do_sample", False)),
        "prefix_allowed_tokens_fn": prefix_fn,
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
