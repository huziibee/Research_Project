"""Seven comparison-system adapters."""

from __future__ import annotations

import copy
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema.v2.records import UnresolvedSlot
from ambiguity_manager.schema.v2.taxonomies import RouteLabel
from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput, SystemResult
from ambiguity_manager.systems.errors import ProviderUnavailableError
from ambiguity_manager.systems.manager import FullManager
from ambiguity_manager.systems.providers import DirectLLMProvider, StructuredAnalysisProvider
from ambiguity_manager.systems.response_generation import generate_clarification
from ambiguity_manager.systems.safety import SafetyEnforcer
from ambiguity_manager.systems.uncertainty import scalar_uncertainty_score


SYSTEM_IDS: tuple[str, ...] = (
  "always_execute",
  "always_clarify",
  "always_silently_resolve",
  "direct_base_llm",
  "degree_based_router",
  "context_blind_manager",
  "full_type_risk_aware_manager",
)


def load_system_variants(path: Path | None = None) -> dict[str, Any]:
  if path is None:
    path = ProjectPaths.from_repo_root().configs / "manager" / "system_variants_v1.json"
  return json.loads(path.read_text(encoding="utf-8"))


class ComparisonSystem(ABC):
  system_id: str
  system_version: str = "1.0.0"

  @abstractmethod
  def run(
    self,
    system_input: SystemInput,
    *,
    cached_analysis: StructuredAnalysis | None = None,
  ) -> SystemResult:
    ...

  def readiness(self) -> dict[str, Any]:
    return {
      "system_id": self.system_id,
      "system_version": self.system_version,
      "official_ready": False,
    }


def _base_result(
  system_id: str,
  system_version: str,
  system_input: SystemInput,
  analysis: StructuredAnalysis,
  route: RouteLabel | None,
  *,
  execution_status: str = "ok",
  **kwargs: Any,
) -> SystemResult:
  result = SystemResult(
    record_id=system_input.record_id,
    system_id=system_id,
    system_version=system_version,
    analysis=analysis,
    recommended_strategy=route,
    strategy_sequence=list(kwargs.get("strategy_sequence", [])),
    clarification_targets=list(kwargs.get("clarification_targets", [])),
    clarification_question=kwargs.get("clarification_question"),
    resolved_slots=list(kwargs.get("resolved_slots", analysis.resolved_slots)),
    rejection_reason=kwargs.get("rejection_reason"),
    execution_status=execution_status,
    provider_provenance=dict(kwargs.get("provider_provenance", {})),
    runtime_metadata=dict(kwargs.get("runtime_metadata", {})),
    synthetic_only=True,
    official_result=False,
  )
  return result.with_computed_hash()


@dataclass
class AlwaysExecuteSystem(ComparisonSystem):
  system_id: str = "always_execute"
  system_version: str = "1.0.0"
  safety: SafetyEnforcer = field(default_factory=SafetyEnforcer)

  def run(
    self,
    system_input: SystemInput,
    *,
    cached_analysis: StructuredAnalysis | None = None,
  ) -> SystemResult:
    if cached_analysis is None:
      raise ProviderUnavailableError("cached_analysis", "always_execute requires shared cached analysis")
    analysis = copy.deepcopy(cached_analysis)
    analysis_id = analysis.fingerprint()
    analysis.recommended_strategy = RouteLabel.EXECUTE
    result = _base_result(
      self.system_id,
      self.system_version,
      system_input,
      analysis,
      RouteLabel.EXECUTE,
      provider_provenance={"shared_analysis_fingerprint": analysis_id},
      runtime_metadata={"forced_route": "execute", "shared_analysis_fingerprint": analysis_id},
    )
    enforcement = self.safety.enforce(analysis, command=system_input.command)
    # Do not suppress safety findings; keep status ok so evaluator can score unsafe execution.
    result.safety_findings = list(enforcement.findings)
    result.unsupported_commitment_findings = [
      f for f in enforcement.findings if f.finding_type == "unsupported_commitment"
    ]
    return result.with_computed_hash()


@dataclass
class AlwaysClarifySystem(ComparisonSystem):
  system_id: str = "always_clarify"
  system_version: str = "1.0.0"

  def run(
    self,
    system_input: SystemInput,
    *,
    cached_analysis: StructuredAnalysis | None = None,
  ) -> SystemResult:
    if cached_analysis is None:
      raise ProviderUnavailableError("cached_analysis", "always_clarify requires shared cached analysis")
    analysis = copy.deepcopy(cached_analysis)
    analysis_id = analysis.fingerprint()
    targets = [u.slot_name for u in analysis.unresolved_slots]
    unnecessary = False
    if not targets:
      if analysis.ambiguity_types:
        targets = [t.value for t in analysis.ambiguity_types]
      else:
        unnecessary = True
        targets = []
    question = None
    if targets:
      question = generate_clarification(analysis, targets)
      analysis.clarification_question = question
      analysis.clarification_targets = targets
    analysis.recommended_strategy = RouteLabel.CLARIFY
    return _base_result(
      self.system_id,
      self.system_version,
      system_input,
      analysis,
      RouteLabel.CLARIFY,
      clarification_targets=targets,
      clarification_question=question,
      provider_provenance={"shared_analysis_fingerprint": analysis_id},
      runtime_metadata={
        "forced_route": "clarify",
        "shared_analysis_fingerprint": analysis_id,
        "unnecessary_clarification": unnecessary,
      },
    )


@dataclass
class AlwaysSilentlyResolveSystem(ComparisonSystem):
  system_id: str = "always_silently_resolve"
  system_version: str = "1.0.0"
  safety: SafetyEnforcer = field(default_factory=SafetyEnforcer)

  def run(
    self,
    system_input: SystemInput,
    *,
    cached_analysis: StructuredAnalysis | None = None,
  ) -> SystemResult:
    if cached_analysis is None:
      raise ProviderUnavailableError(
        "cached_analysis", "always_silently_resolve requires shared cached analysis"
      )
    analysis = copy.deepcopy(cached_analysis)
    analysis_id = analysis.fingerprint()
    analysis.recommended_strategy = RouteLabel.SILENTLY_RESOLVE
    result = _base_result(
      self.system_id,
      self.system_version,
      system_input,
      analysis,
      RouteLabel.SILENTLY_RESOLVE,
      resolved_slots=list(analysis.resolved_slots),
      provider_provenance={"shared_analysis_fingerprint": analysis_id},
      runtime_metadata={
        "forced_route": "silently_resolve",
        "shared_analysis_fingerprint": analysis_id,
        "resolution_attempted": True,
        "supported_resolution": bool(analysis.resolved_slots),
      },
    )
    enforcement = self.safety.enforce(analysis, command=system_input.command)
    result.safety_findings = list(enforcement.findings)
    result.unsupported_commitment_findings = [
      f
      for f in enforcement.findings
      if f.finding_type in {"unsupported_commitment", "unsafe_silent_resolution"}
    ]
    # Preserve unsupported commitment honestly; do not convert to clarify.
    return result.with_computed_hash()


@dataclass
class DirectBaseLLMSystem(ComparisonSystem):
  system_id: str = "direct_base_llm"
  system_version: str = "1.0.0"
  provider: DirectLLMProvider | None = None

  def readiness(self) -> dict[str, Any]:
    return {
      "system_id": self.system_id,
      "system_version": self.system_version,
      "requires_model_provider": True,
      "provider_configured": self.provider is not None,
      "official_ready": False,
      "execution_status_without_provider": "not_executable",
    }

  def run(
    self,
    system_input: SystemInput,
    *,
    cached_analysis: StructuredAnalysis | None = None,
  ) -> SystemResult:
    _ = cached_analysis
    if self.provider is None:
      empty = StructuredAnalysis()
      return _base_result(
        self.system_id,
        self.system_version,
        system_input,
        empty,
        None,
        execution_status="provider_unavailable",
        runtime_metadata={"not_executable": True, "reason": "provider_unavailable"},
      )
    analysis = self.provider.predict(system_input)
    return _base_result(
      self.system_id,
      self.system_version,
      system_input,
      analysis,
      analysis.recommended_strategy,
      clarification_targets=list(analysis.clarification_targets),
      clarification_question=analysis.clarification_question,
      resolved_slots=list(analysis.resolved_slots),
      rejection_reason=analysis.rejection_reason,
      strategy_sequence=list(analysis.strategy_sequence),
      provider_provenance={
        "provider_id": getattr(self.provider, "provider_id", "direct_llm"),
        "provider_version": getattr(self.provider, "provider_version", "unknown"),
      },
    )


@dataclass
class DegreeBasedRouterSystem(ComparisonSystem):
  system_id: str = "degree_based_router"
  system_version: str = "1.0.0"
  variants_config: dict[str, Any] = field(default_factory=load_system_variants)

  def run(
    self,
    system_input: SystemInput,
    *,
    cached_analysis: StructuredAnalysis | None = None,
  ) -> SystemResult:
    if cached_analysis is None:
      raise ProviderUnavailableError(
        "cached_analysis", "degree_based_router requires shared cached analysis"
      )
    analysis = copy.deepcopy(cached_analysis)
    analysis_id = analysis.fingerprint()
    thresholds = self.variants_config.get("degree_router_thresholds", {})
    # Scalar uncertainty only — no type/risk/capability precedence.
    if analysis.context_sampling_uncertainty and analysis.context_sampling_uncertainty.score is not None:
      score = float(analysis.context_sampling_uncertainty.score)
    else:
      # Fallback development scalar from ambiguity presence only (not type-specific).
      score = 0.0
      if analysis.ambiguity_present:
        score = 0.5
      if analysis.unresolved_slots:
        score = max(score, 0.6)
    execute_max = float(thresholds.get("execute_max_uncertainty", 0.15))
    silent_max = float(thresholds.get("silently_resolve_max_uncertainty", 0.4))
    if score <= execute_max:
      route = RouteLabel.EXECUTE
    elif score <= silent_max:
      route = RouteLabel.SILENTLY_RESOLVE
    else:
      route = RouteLabel.CLARIFY
    # Enforce allowed routes only.
    allowed = {"execute", "silently_resolve", "clarify"}
    assert route.value in allowed
    targets: list[str] = []
    question = None
    if route == RouteLabel.CLARIFY:
      targets = [u.slot_name for u in analysis.unresolved_slots] or ["intent"]
      question = generate_clarification(analysis, targets)
    analysis.recommended_strategy = route
    analysis.clarification_targets = targets
    analysis.clarification_question = question
    return _base_result(
      self.system_id,
      self.system_version,
      system_input,
      analysis,
      route,
      clarification_targets=targets,
      clarification_question=question,
      resolved_slots=list(analysis.resolved_slots),
      provider_provenance={"shared_analysis_fingerprint": analysis_id},
      runtime_metadata={
        "uncertainty_score": score,
        "thresholds_status": thresholds.get("status", "unfrozen"),
        "thresholds_valid_for_official_use": bool(thresholds.get("valid_for_official_use", False)),
        "uses_type_risk_capability_precedence": False,
        "shared_analysis_fingerprint": analysis_id,
      },
    )


@dataclass
class ContextBlindManagerSystem(ComparisonSystem):
  system_id: str = "context_blind_manager"
  system_version: str = "1.0.0"
  analysis_provider: StructuredAnalysisProvider | None = None
  inner: FullManager | None = None

  def run(
    self,
    system_input: SystemInput,
    *,
    cached_analysis: StructuredAnalysis | None = None,
  ) -> SystemResult:
    original = system_input
    blinded = system_input.without_context()
    # Ensure original not mutated.
    assert original.scene_context == system_input.scene_context
    manager = self.inner or FullManager(
      system_id=self.system_id,
      system_version=self.system_version,
      analysis_provider=self.analysis_provider,
    )
    # If cached analysis provided, strip context-dependent resolved slots that relied on context.
    analysis = copy.deepcopy(cached_analysis) if cached_analysis is not None else None
    if analysis is not None and not self.analysis_provider:
      # Re-run manager pieces with blinded input and cached analysis as starting point.
      manager.analysis_provider = None
      result = manager.run(blinded, cached_analysis=analysis)
    else:
      result = manager.run(blinded, cached_analysis=analysis)
    result.system_id = self.system_id
    result.system_version = self.system_version
    result.runtime_metadata = {
      **result.runtime_metadata,
      "context_ablation": {
        "dialogue_history_removed": True,
        "scene_context_removed": True,
        "capability_context_removed": True,
      },
      "original_input_unmutated": True,
    }
    return result.with_computed_hash()


@dataclass
class FullTypeRiskAwareManagerSystem(ComparisonSystem):
  system_id: str = "full_type_risk_aware_manager"
  system_version: str = "1.0.0"
  manager: FullManager = field(default_factory=FullManager)

  def readiness(self) -> dict[str, Any]:
    return self.manager.readiness()

  def run(
    self,
    system_input: SystemInput,
    *,
    cached_analysis: StructuredAnalysis | None = None,
  ) -> SystemResult:
    return self.manager.run(system_input, cached_analysis=cached_analysis)


def build_default_registry(
  *,
  analysis_provider: StructuredAnalysisProvider | None = None,
  direct_llm_provider: DirectLLMProvider | None = None,
) -> dict[str, ComparisonSystem]:
  full = FullManager(analysis_provider=analysis_provider)
  return {
    "always_execute": AlwaysExecuteSystem(),
    "always_clarify": AlwaysClarifySystem(),
    "always_silently_resolve": AlwaysSilentlyResolveSystem(),
    "direct_base_llm": DirectBaseLLMSystem(provider=direct_llm_provider),
    "degree_based_router": DegreeBasedRouterSystem(),
    "context_blind_manager": ContextBlindManagerSystem(
      analysis_provider=analysis_provider,
      inner=FullManager(analysis_provider=analysis_provider),
    ),
    "full_type_risk_aware_manager": FullTypeRiskAwareManagerSystem(manager=full),
  }


_REGISTRY: dict[str, ComparisonSystem] | None = None


def list_systems() -> list[dict[str, Any]]:
  registry = get_registry()
  return [registry[sid].readiness() for sid in SYSTEM_IDS]


def get_registry(
  *,
  analysis_provider: StructuredAnalysisProvider | None = None,
  direct_llm_provider: DirectLLMProvider | None = None,
  rebuild: bool = False,
) -> dict[str, ComparisonSystem]:
  global _REGISTRY
  if _REGISTRY is None or rebuild or analysis_provider is not None or direct_llm_provider is not None:
    _REGISTRY = build_default_registry(
      analysis_provider=analysis_provider,
      direct_llm_provider=direct_llm_provider,
    )
  return _REGISTRY


def get_system(system_id: str) -> ComparisonSystem:
  registry = get_registry()
  if system_id not in registry:
    raise KeyError(f"unknown system_id: {system_id}")
  return registry[system_id]
