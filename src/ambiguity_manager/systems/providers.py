"""Provider protocols for model-backed system components."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput
from ambiguity_manager.systems.errors import ProviderUnavailableError


@runtime_checkable
class StructuredAnalysisProvider(Protocol):
  provider_id: str
  provider_version: str

  def analyse(self, system_input: SystemInput) -> StructuredAnalysis:
    ...


@runtime_checkable
class CandidateInterpretationProvider(Protocol):
  provider_id: str
  provider_version: str

  def generate_candidates(
    self,
    system_input: SystemInput,
    initial_analysis: StructuredAnalysis | None = None,
  ) -> StructuredAnalysis:
    ...


@runtime_checkable
class ClarificationProvider(Protocol):
  provider_id: str
  provider_version: str

  def generate_clarification(
    self,
    analysis: StructuredAnalysis,
    clarification_targets: list[str],
  ) -> str:
    ...


@runtime_checkable
class RejectionProvider(Protocol):
  provider_id: str
  provider_version: str

  def generate_rejection(
    self,
    analysis: StructuredAnalysis,
    rejection_reason: str,
  ) -> str:
    ...


@runtime_checkable
class DirectLLMProvider(Protocol):
  provider_id: str
  provider_version: str

  def predict(self, system_input: SystemInput) -> StructuredAnalysis:
    ...


@dataclass
class DeterministicAnalysisProvider:
  """In-memory deterministic provider for synthetic fixtures."""

  analyses_by_record: dict[str, StructuredAnalysis]
  provider_id: str = "deterministic_analysis"
  provider_version: str = "1.0.0"

  def analyse(self, system_input: SystemInput) -> StructuredAnalysis:
    if system_input.record_id not in self.analyses_by_record:
      raise ProviderUnavailableError(
        self.provider_id,
        f"no deterministic analysis for record_id={system_input.record_id}",
      )
    return self.analyses_by_record[system_input.record_id]


@dataclass
class DeterministicCandidateProvider:
  provider_id: str = "deterministic_candidates"
  provider_version: str = "1.0.0"
  analyses_by_record: dict[str, StructuredAnalysis] = field(default_factory=dict)

  def generate_candidates(
    self,
    system_input: SystemInput,
    initial_analysis: StructuredAnalysis | None = None,
  ) -> StructuredAnalysis:
    if system_input.record_id in self.analyses_by_record:
      return self.analyses_by_record[system_input.record_id]
    if initial_analysis is not None:
      return initial_analysis
    raise ProviderUnavailableError(
      self.provider_id,
      f"no candidate analysis for record_id={system_input.record_id}",
    )


@dataclass
class UnavailableProvider:
  """Honest failure stub for unconfigured model-backed providers."""

  provider_name: str
  provider_id: str = "unavailable"
  provider_version: str = "0.0.0"

  def analyse(self, system_input: SystemInput) -> StructuredAnalysis:
    raise ProviderUnavailableError(self.provider_name)

  def generate_candidates(
    self,
    system_input: SystemInput,
    initial_analysis: StructuredAnalysis | None = None,
  ) -> StructuredAnalysis:
    raise ProviderUnavailableError(self.provider_name)

  def generate_clarification(
    self,
    analysis: StructuredAnalysis,
    clarification_targets: list[str],
  ) -> str:
    raise ProviderUnavailableError(self.provider_name)

  def generate_rejection(
    self,
    analysis: StructuredAnalysis,
    rejection_reason: str,
  ) -> str:
    raise ProviderUnavailableError(self.provider_name)

  def predict(self, system_input: SystemInput) -> StructuredAnalysis:
    raise ProviderUnavailableError(self.provider_name)


def require_provider(provider: Any, name: str) -> Any:
  if provider is None:
    raise ProviderUnavailableError(name)
  return provider
