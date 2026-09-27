"""Full type/risk-aware manager pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ambiguity_manager.schema.v2.taxonomies import RouteLabel
from ambiguity_manager.systems.analysis import analysis_from_cached
from ambiguity_manager.systems.classification import apply_classification_aggregate, derive_ambiguity_fields
from ambiguity_manager.systems.context_resolution import ContextResolver
from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput, SystemResult
from ambiguity_manager.systems.errors import ProviderUnavailableError
from ambiguity_manager.systems.providers import StructuredAnalysisProvider
from ambiguity_manager.systems.response_generation import generate_clarification, generate_rejection
from ambiguity_manager.systems.routing import DeterministicRouter, apply_router_decision
from ambiguity_manager.systems.safety import SafetyEnforcer, load_safety_policy
from ambiguity_manager.systems.uncertainty import UncertaintyDiagnostics, compute_uncertainty_diagnostics


@dataclass
class FullManager:
  system_id: str = "full_type_risk_aware_manager"
  system_version: str = "1.0.0"
  analysis_provider: StructuredAnalysisProvider | None = None
  router: DeterministicRouter = field(default_factory=DeterministicRouter)
  resolver: ContextResolver = field(default_factory=ContextResolver)
  safety: SafetyEnforcer = field(default_factory=SafetyEnforcer)
  uncertainty_samples: list[StructuredAnalysis] = field(default_factory=list)
  synthetic_only: bool = True

  def readiness(self) -> dict[str, Any]:
    return {
      "system_id": self.system_id,
      "system_version": self.system_version,
      "requires_model_provider": False,
      "provider_configured": self.analysis_provider is not None,
      "awaits_t28_adapter": True,
      "official_ready": False,
      "empirically_complete": False,
    }

  def run(
    self,
    system_input: SystemInput,
    *,
    cached_analysis: StructuredAnalysis | None = None,
  ) -> SystemResult:
    if cached_analysis is not None:
      # Treat cached analysis as immutable input.
      analysis = analysis_from_cached(cached_analysis)
      provider_prov = {"provider_id": "cached_analysis", "provider_version": "1.0.0"}
    elif self.analysis_provider is not None:
      # Provider returns a copy; still isolate the working object.
      analysis = analysis_from_cached(self.analysis_provider.analyse(system_input))
      provider_prov = {
        "provider_id": getattr(self.analysis_provider, "provider_id", "analysis_provider"),
        "provider_version": getattr(self.analysis_provider, "provider_version", "unknown"),
      }
    else:
      raise ProviderUnavailableError(
        "StructuredAnalysisProvider",
        "full manager requires a configured analysis provider or cached analysis",
      )

    # Context resolution before routing (resolver.apply returns a new working copy).
    resolution = self.resolver.resolve(system_input, analysis)
    analysis = self.resolver.apply(analysis, resolution)

    # Classification aggregate
    aggregate = derive_ambiguity_fields(analysis)
    analysis = apply_classification_aggregate(analysis, aggregate)

    # Optional uncertainty over supplied samples
    uncertainty: UncertaintyDiagnostics | None = None
    if self.uncertainty_samples:
      uncertainty = compute_uncertainty_diagnostics(self.uncertainty_samples)
      if analysis.context_sampling_uncertainty is None:
        from ambiguity_manager.schema.v2.records import ContextSamplingUncertainty
        from ambiguity_manager.systems.uncertainty import scalar_uncertainty_score

        analysis.context_sampling_uncertainty = ContextSamplingUncertainty(
          score=scalar_uncertainty_score(uncertainty),
          variant_count=uncertainty.total_sample_count,
          agreement=1.0 - scalar_uncertainty_score(uncertainty),
        )

    decision = self.router.route(analysis)
    try:
      self.router.validate_decision(decision, analysis)
    except Exception as exc:  # noqa: BLE001 - convert to safety finding path
      analysis.findings = list(analysis.findings) + [f"router_validation:{exc}"]

    analysis = apply_router_decision(analysis, decision)

    clarification_question = None
    rejection_text = None
    scene_for_clarify = getattr(system_input, "scene_context", None)
    if decision.recommended_strategy == RouteLabel.CLARIFY:
      clarification_question = generate_clarification(
        analysis,
        decision.clarification_targets,
        scene_context=scene_for_clarify,
      )
      analysis.clarification_question = clarification_question
    elif decision.recommended_strategy == RouteLabel.FACE_PRESERVING_REJECTION:
      rejection_text = generate_rejection(
        analysis, decision.rejection_reason or "capability_limitation"
      )
    elif decision.recommended_strategy == RouteLabel.MULTI_STEP:
      if RouteLabel.CLARIFY in decision.strategy_sequence:
        clarification_question = generate_clarification(
          analysis,
          decision.clarification_targets,
          scene_context=scene_for_clarify,
        )
        analysis.clarification_question = clarification_question

    response_text = clarification_question or rejection_text
    enforcement = self.safety.enforce(
      analysis,
      decision=decision,
      response_text=response_text,
      command=system_input.command,
    )

    result = SystemResult(
      record_id=system_input.record_id,
      system_id=self.system_id,
      system_version=self.system_version,
      analysis=analysis,
      recommended_strategy=decision.recommended_strategy,
      strategy_sequence=list(decision.strategy_sequence),
      clarification_targets=list(decision.clarification_targets),
      clarification_question=clarification_question,
      resolved_slots=list(analysis.resolved_slots),
      rejection_reason=decision.rejection_reason,
      execution_status="ok",
      provider_provenance=provider_prov,
      runtime_metadata={
        "router_trace": decision.to_dict(),
        "resolution_events": [e.to_dict() for e in resolution.events],
        "classification": aggregate.to_dict(),
        "uncertainty": uncertainty.to_dict() if uncertainty else None,
        "rejection_text": rejection_text,
        "safety_action": enforcement.action,
        "requires_re_evaluation": decision.requires_re_evaluation,
        "awaits_t28_adapter": True,
      },
      # Runner owns official/synthetic flags; adapters must not override validated mode.
      synthetic_only=self.synthetic_only,
      official_result=False,
    )
    result = self.safety.apply_to_result(result, enforcement)
    return result


@dataclass
class GoalFirstManager(FullManager):
  """Future manager: do the task when capable and low-risk, even if some ambiguity remains.

  Frozen T39 still uses FullManager / t39_conservative. This class is a new system.
  """

  system_id: str = "goal_first_manager_v1"
  system_version: str = "1.0.0"
  router: DeterministicRouter = field(
    default_factory=lambda: DeterministicRouter(policy="goal_first_v1")
  )


@dataclass
class GoalFirstManagerV2(FullManager):
  """Separately versioned manager: fill goal+CPC, then act unless unsafe/incapable.

  Frozen T39 still uses FullManager / t39_conservative. Safety records findings
  but does not fail-closed-reject a context-licensed execute.
  """

  system_id: str = "goal_first_manager_v2"
  system_version: str = "2.0.0"
  router: DeterministicRouter = field(
    default_factory=lambda: DeterministicRouter(policy="goal_first_v2")
  )
  safety: SafetyEnforcer = field(
    default_factory=lambda: SafetyEnforcer(
      policy={**load_safety_policy(), "enforcement_mode": "record_findings"}
    )
  )
