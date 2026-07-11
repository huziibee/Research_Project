"""Context budget calculation for bounded generation."""

from __future__ import annotations

DEFAULT_SAFETY_MARGIN = 128


class ContextBudgetError(Exception):
    """Raised when generation capacity cannot be determined or is non-positive."""


def compute_effective_max_new_tokens(
    *,
    requested_max_new_tokens: int,
    model_context_limit: int | None,
    prompt_token_count: int | None,
    safety_margin: int = DEFAULT_SAFETY_MARGIN,
) -> int:
    if model_context_limit is None:
        raise ContextBudgetError("model_context_limit is unknown")
    if prompt_token_count is None:
        raise ContextBudgetError("prompt_token_count is unknown")
    if requested_max_new_tokens <= 0:
        raise ContextBudgetError("requested_max_new_tokens must be positive")

    available = model_context_limit - prompt_token_count - safety_margin
    if available <= 0:
        raise ContextBudgetError("no positive generation capacity remains")
    return min(requested_max_new_tokens, available)
