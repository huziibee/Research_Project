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


class ResumeContractError(SystemsContractError):
  """Raised when a resume request's identity does not match the original run.

  A resume must be provably a continuation of the same run: same run_mode,
  config, input manifest (for already-completed records), systems/versions,
  provider/model identities, evaluator version, source commit, and an
  existing-results/expected-matrix that is still internally consistent.
  Any mismatch is refused rather than silently accepted.
  """

  def __init__(self, mismatches: list[str]) -> None:
    self.mismatches = list(mismatches)
    joined = "; ".join(self.mismatches) if self.mismatches else "unknown mismatch"
    super().__init__(f"resume contract violated: {joined}")


class ProtectedDataBlockedError(RuntimeError):
  """Raised when a protected-data record is presented outside official mode."""

  def __init__(self, record_id: str, run_mode: str) -> None:
    self.record_id = record_id
    self.run_mode = run_mode
    super().__init__(
      f"protected_data record {record_id!r} is blocked in run_mode={run_mode!r}; "
      "protected records may only be processed in run_mode='official'"
    )


class ContextAblationError(SystemsContractError):
  """Raised when context-blind execution would consume incompatible analysis."""


class EvaluationContractError(SystemsContractError):
  """Raised when evaluation inputs violate contract (duplicates, mixed overwrite)."""
