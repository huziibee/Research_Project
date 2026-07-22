"""Deterministic candidate-interpretation service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ambiguity_manager.schema.v2.records import (
  CPC,
  CandidateInterpretationFrame,
  EvidenceRef,
  SelectedInterpretation,
  UnresolvedSlot,
)
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES, CPCSlotStatus
from ambiguity_manager.systems.contracts import AnalysisProvenance, StructuredAnalysis, SystemInput
from ambiguity_manager.systems.errors import SystemsContractError
from ambiguity_manager.systems.hashing import sha256_json
from ambiguity_manager.systems.providers import CandidateInterpretationProvider, require_provider

CRITICAL_SLOTS: tuple[str, ...] = (
  "action",
  "object",
  "destination",
  "tool",
  "conditions",
  "constraints",
)


def _filled_slots(cpc: CPC) -> dict[str, str]:
  filled: dict[str, str] = {}
  for name in CPC_SLOT_NAMES:
    slot = getattr(cpc, name)
    if slot.status == CPCSlotStatus.FILLED and isinstance(slot.value, str) and slot.value.strip():
      filled[name] = slot.value.strip().lower()
  return filled


def material_cpc_fingerprint(cpc: CPC) -> str:
  return sha256_json(_filled_slots(cpc))


def candidate_set_fingerprint(candidates: list[CandidateInterpretationFrame]) -> str:
  """Order-independent, ID-independent semantic fingerprint of a candidate set.

  Two candidate sets with identical CPC content match even if their
  ``frame_id`` values differ or the candidates are listed in a different
  order. ``frame_id`` and free-text ``text`` are deliberately excluded
  because they are arbitrary labels, not material content; only the filled
  CPC slots and safety status are semantically load-bearing.
  """
  items = sorted(
    material_cpc_fingerprint(c.cpc) + ":" + (c.safety_status.value if c.safety_status else "")
    for c in candidates
  )
  return sha256_json(items)


@dataclass
class CandidateInterpretationService:
  """Validate and fingerprint candidate interpretations around a provider contract."""

  provider: CandidateInterpretationProvider | None = None
  allow_duplicate_material: bool = False

  def validate_candidates(
    self,
    candidates: list[CandidateInterpretationFrame],
    *,
    selected: SelectedInterpretation | None = None,
    unresolved: list[UnresolvedSlot] | None = None,
    supporting_evidence: list[EvidenceRef] | None = None,
  ) -> list[str]:
    findings: list[str] = []
    seen_ids: set[str] = set()
    material_seen: dict[str, str] = {}
    for candidate in candidates:
      if not candidate.frame_id or not candidate.frame_id.strip():
        findings.append("empty_candidate_id")
        continue
      if candidate.frame_id in seen_ids:
        findings.append(f"duplicate_candidate_id:{candidate.frame_id}")
      seen_ids.add(candidate.frame_id)
      material = material_cpc_fingerprint(candidate.cpc)
      if material in material_seen and not self.allow_duplicate_material:
        findings.append(
          f"exact_duplicate_interpretation:{material_seen[material]}->{candidate.frame_id}"
        )
      else:
        material_seen[material] = candidate.frame_id
      filled = _filled_slots(candidate.cpc)
      if not filled and not (candidate.text and candidate.text.strip()):
        findings.append(f"empty_candidate:{candidate.frame_id}")
    if selected is not None:
      if selected.frame_id not in seen_ids:
        findings.append(f"selected_missing_from_candidates:{selected.frame_id}")
      if not selected.supporting_evidence:
        findings.append("selected_interpretation_missing_evidence")
    unresolved = unresolved or []
    for slot in unresolved:
      if slot.slot_name in CRITICAL_SLOTS:
        findings.append(f"unresolved_critical_slot:{slot.slot_name}")
    _ = supporting_evidence
    return findings

  def detect_unsupported_specificity(
    self,
    candidate: CandidateInterpretationFrame,
    system_input: SystemInput,
    *,
    allowed_values: dict[str, set[str]] | None = None,
  ) -> list[str]:
    findings: list[str] = []
    allowed_values = allowed_values or {}
    command_l = system_input.command.lower()
    scene_l = (system_input.scene_context or "").lower()
    dialogue_l = " ".join(system_input.dialogue_history).lower()
    for name, value in _filled_slots(candidate.cpc).items():
      if name in allowed_values and value not in {v.lower() for v in allowed_values[name]}:
        findings.append(f"unsupported_specificity:{name}={value}")
        continue
      if value not in command_l and value not in scene_l and value not in dialogue_l:
        # Only flag when the value is asserted as filled but absent from all context sources.
        if name in CRITICAL_SLOTS:
          findings.append(f"unsupported_specificity:{name}={value}")
    return findings

  def build_analysis(
    self,
    *,
    candidates: list[CandidateInterpretationFrame],
    selected: SelectedInterpretation | None = None,
    unresolved: list[UnresolvedSlot] | None = None,
    supporting_evidence: list[EvidenceRef] | None = None,
    base: StructuredAnalysis | None = None,
    system_input: SystemInput | None = None,
    allowed_values: dict[str, set[str]] | None = None,
  ) -> StructuredAnalysis:
    unresolved = unresolved or []
    supporting_evidence = supporting_evidence or []
    findings = self.validate_candidates(
      candidates,
      selected=selected,
      unresolved=unresolved,
      supporting_evidence=supporting_evidence,
    )
    unsupported: list[str] = []
    if system_input is not None:
      for candidate in candidates:
        unsupported.extend(
          self.detect_unsupported_specificity(
            candidate, system_input, allowed_values=allowed_values
          )
        )
    analysis = base or StructuredAnalysis()
    analysis.candidate_interpretations = list(candidates)
    analysis.selected_interpretation = selected
    analysis.unresolved_slots = list(unresolved)
    analysis.supporting_evidence = list(supporting_evidence)
    analysis.unsupported_specificity = unsupported
    analysis.findings = findings + unsupported
    analysis.analysis_provenance = AnalysisProvenance(
      provider_id="candidate_interpretation_service",
      provider_version="1.0.0",
      method="deterministic",
      notes=f"candidate_set_fingerprint={candidate_set_fingerprint(candidates)}",
    )
    if selected is None and len(candidates) > 1:
      analysis.ambiguity_present = True
    return analysis

  def run(
    self,
    system_input: SystemInput,
    initial_analysis: StructuredAnalysis | None = None,
  ) -> StructuredAnalysis:
    provider = require_provider(self.provider, "CandidateInterpretationProvider")
    return provider.generate_candidates(system_input, initial_analysis)


@dataclass
class CandidateSetReport:
  fingerprint: str
  candidate_ids: list[str]
  findings: list[str]
  unresolved_critical_slots: list[str]
  selected_frame_id: str | None = None

  def to_dict(self) -> dict[str, Any]:
    return {
      "fingerprint": self.fingerprint,
      "candidate_ids": list(self.candidate_ids),
      "findings": list(self.findings),
      "unresolved_critical_slots": list(self.unresolved_critical_slots),
      "selected_frame_id": self.selected_frame_id,
    }


def report_candidate_set(analysis: StructuredAnalysis) -> CandidateSetReport:
  service = CandidateInterpretationService()
  findings = service.validate_candidates(
    analysis.candidate_interpretations,
    selected=analysis.selected_interpretation,
    unresolved=analysis.unresolved_slots,
    supporting_evidence=analysis.supporting_evidence,
  )
  unresolved_critical = [
    u.slot_name for u in analysis.unresolved_slots if u.slot_name in CRITICAL_SLOTS
  ]
  return CandidateSetReport(
    fingerprint=candidate_set_fingerprint(analysis.candidate_interpretations),
    candidate_ids=[c.frame_id for c in analysis.candidate_interpretations],
    findings=findings,
    unresolved_critical_slots=unresolved_critical,
    selected_frame_id=(
      analysis.selected_interpretation.frame_id if analysis.selected_interpretation else None
    ),
  )


def require_unique_candidate_ids(candidates: list[CandidateInterpretationFrame]) -> None:
  ids = [c.frame_id for c in candidates]
  if len(ids) != len(set(ids)):
    raise SystemsContractError("duplicate candidate IDs are not allowed")
