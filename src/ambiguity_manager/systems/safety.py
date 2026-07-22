"""Safety enforcement layer for analysis/routing/response."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema.v2.taxonomies import CapabilityStatus, RiskLevel, RouteLabel
from ambiguity_manager.systems.candidate_generation import CRITICAL_SLOTS
from ambiguity_manager.systems.contracts import SafetyFinding, StructuredAnalysis, SystemResult
from ambiguity_manager.systems.routing import RouterDecision


def load_safety_policy(path: Path | None = None) -> dict[str, Any]:
  if path is None:
    path = ProjectPaths.from_repo_root().configs / "manager" / "safety_policy_v1.json"
  return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class SafetyEnforcementResult:
  findings: list[SafetyFinding] = field(default_factory=list)
  action: str = "return_with_findings"
  reject: bool = False

  def to_dict(self) -> dict[str, Any]:
    return {
      "findings": [f.to_dict() for f in self.findings],
      "action": self.action,
      "reject": self.reject,
    }


class SafetyEnforcer:
  def __init__(self, policy: dict[str, Any] | None = None) -> None:
    self.policy = policy or load_safety_policy()
    self.fail_closed = self.policy.get("enforcement_mode", "fail_closed") == "fail_closed"

  def check_analysis(self, analysis: StructuredAnalysis) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    if analysis.selected_interpretation is not None:
      if not analysis.selected_interpretation.supporting_evidence:
        findings.append(
          SafetyFinding(
            finding_type="unsupported_commitment",
            message="selected interpretation lacks supporting evidence",
          )
        )
      selected_ids = {c.frame_id for c in analysis.candidate_interpretations}
      if analysis.selected_interpretation.frame_id not in selected_ids and selected_ids:
        findings.append(
          SafetyFinding(
            finding_type="unsupported_commitment",
            message="selected interpretation not present in candidates",
          )
        )
    for item in analysis.unsupported_specificity:
      findings.append(
        SafetyFinding(
          finding_type="extra_specificity",
          message=item,
        )
      )
    if analysis.capability_status == CapabilityStatus.INCAPABLE and analysis.recommended_strategy == RouteLabel.EXECUTE:
      findings.append(
        SafetyFinding(
          finding_type="capability_overcommitment",
          message="execute requested despite known incapability",
        )
      )
    return findings

  def check_route(
    self,
    analysis: StructuredAnalysis,
    decision: RouterDecision | None = None,
    *,
    recommended: RouteLabel | None = None,
    strategy_sequence: list[RouteLabel] | None = None,
    clarification_targets: list[str] | None = None,
    rejection_reason: str | None = None,
    resolved_slots: list | None = None,
  ) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    route = recommended or (decision.recommended_strategy if decision else analysis.recommended_strategy)
    sequence = strategy_sequence
    if sequence is None:
      sequence = decision.strategy_sequence if decision else analysis.strategy_sequence
    targets = clarification_targets
    if targets is None:
      targets = decision.clarification_targets if decision else analysis.clarification_targets
    reason = rejection_reason
    if reason is None:
      reason = decision.rejection_reason if decision else analysis.rejection_reason
    resolved = resolved_slots if resolved_slots is not None else analysis.resolved_slots
    unresolved_critical = [
      u.slot_name for u in analysis.unresolved_slots if u.slot_name in CRITICAL_SLOTS
    ]

    if route == RouteLabel.SILENTLY_RESOLVE:
      if not resolved:
        findings.append(
          SafetyFinding(
            finding_type="unsafe_silent_resolution",
            message="silent resolution without resolved slot values",
          )
        )
      if not analysis.resolution_evidence and not analysis.supporting_evidence:
        findings.append(
          SafetyFinding(
            finding_type="unsafe_silent_resolution",
            message="silent resolution without evidence",
          )
        )
      if analysis.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH) and unresolved_critical:
        findings.append(
          SafetyFinding(
            finding_type="unsafe_silent_resolution",
            message="high-risk unresolved slot under silent resolve",
            details={"unresolved": unresolved_critical},
          )
        )

    if route == RouteLabel.EXECUTE and unresolved_critical:
      findings.append(
        SafetyFinding(
          finding_type="unresolved_critical_execution",
          message="execute with unresolved critical slots",
          details={"unresolved": unresolved_critical},
        )
      )

    if route == RouteLabel.CLARIFY and not targets:
      findings.append(
        SafetyFinding(
          finding_type="invalid_clarification",
          message="clarification with no target",
        )
      )

    if route == RouteLabel.FACE_PRESERVING_REJECTION and not reason:
      findings.append(
        SafetyFinding(
          finding_type="invalid_rejection",
          message="rejection without an applicable reason",
        )
      )

    if route == RouteLabel.MULTI_STEP:
      if len(sequence or []) < 2:
        findings.append(
          SafetyFinding(
            finding_type="strategy_sequence_violation",
            message="multi_step requires strategy_sequence length >= 2",
          )
        )
      if RouteLabel.SILENTLY_RESOLVE in (sequence or []) and analysis.risk_level in (
        RiskLevel.MEDIUM,
        RiskLevel.HIGH,
      ):
        findings.append(
          SafetyFinding(
            finding_type="strategy_sequence_violation",
            message="unsafe strategy sequence includes silent resolve under elevated risk",
          )
        )

    if analysis.capability_status == CapabilityStatus.INCAPABLE and route == RouteLabel.EXECUTE:
      findings.append(
        SafetyFinding(
          finding_type="capability_overcommitment",
          message="impossible capability commitment",
        )
      )

    return findings

  def check_response_specificity(
    self,
    text: str | None,
    analysis: StructuredAnalysis,
    system_command: str,
  ) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    if not text:
      return findings
    # Detect invented proper nouns not present in command/candidates/resolved values.
    allowed = {system_command.lower()}
    for cand in analysis.candidate_interpretations:
      if cand.text:
        allowed.add(cand.text.lower())
      for name in CRITICAL_SLOTS:
        slot = getattr(cand.cpc, name)
        if slot.value:
          allowed.add(slot.value.lower())
    for resolved in analysis.resolved_slots:
      allowed.add(resolved.value.lower())
    tokens = [t.strip(".,?!") for t in text.split() if t[:1].isupper() and len(t) > 3]
    for token in tokens:
      if token.lower() not in " ".join(allowed) and token.lower() not in {
        "which",
        "should",
        "before",
        "please",
        "sorry",
      }:
        # Only flag if token looks like an entity and is absent from allowed blobs.
        blob = " ".join(allowed)
        if token.lower() not in blob:
          findings.append(
            SafetyFinding(
              finding_type="extra_specificity",
              message=f"response introduces unsupported specificity: {token}",
            )
          )
    return findings

  def enforce(
    self,
    analysis: StructuredAnalysis,
    *,
    decision: RouterDecision | None = None,
    response_text: str | None = None,
    command: str = "",
  ) -> SafetyEnforcementResult:
    findings = []
    findings.extend(self.check_analysis(analysis))
    findings.extend(self.check_route(analysis, decision))
    findings.extend(self.check_response_specificity(response_text, analysis, command))
    reject = self.fail_closed and any(f.severity == "error" for f in findings)
    action = "reject_result" if reject else "return_with_findings"
    # Hard fail-closed only for critical finding types
    critical_types = {
      "unsafe_silent_resolution",
      "unresolved_critical_execution",
      "capability_overcommitment",
      "strategy_sequence_violation",
    }
    if self.fail_closed and any(f.finding_type in critical_types for f in findings):
      reject = True
      action = "reject_result"
    return SafetyEnforcementResult(findings=findings, action=action, reject=reject)

  def apply_to_result(
    self,
    result: SystemResult,
    enforcement: SafetyEnforcementResult,
  ) -> SystemResult:
    result.safety_findings = list(enforcement.findings)
    result.unsupported_commitment_findings = [
      f for f in enforcement.findings if f.finding_type == "unsupported_commitment"
    ]
    if enforcement.reject:
      result.execution_status = "rejected_by_safety"
    return result.with_computed_hash()
