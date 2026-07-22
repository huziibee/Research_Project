"""Typed errors for the model-independent systems package."""

from __future__ import annotations


class SystemsContractError(ValueError):
  """Raised when a systems contract payload is invalid."""


class ProviderUnavailableError(RuntimeError):
  """Raised when a required model/provider backend is not configured."""

  def __init__(self, provider_name: str, message: str | None = None) -> None:
    self.provider_name = provider_name
    detail = message or f"provider unavailable: {provider_name}"
    super().__init__(detail)


class OfficialRunBlockedError(RuntimeError):
  """Raised when an official experiment run is missing required artefacts."""

  def __init__(self, missing: list[str]) -> None:
    self.missing = list(missing)
    joined = "; ".join(self.missing) if self.missing else "unknown prerequisites"
    super().__init__(f"official run blocked: {joined}")


class DuplicateResultError(RuntimeError):
  """Raised when a runner would overwrite or duplicate a completed result."""
