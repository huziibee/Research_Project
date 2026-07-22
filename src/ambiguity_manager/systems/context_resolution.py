"""Deterministic context resolver."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema.v2.records import EvidenceRef, ResolvedSlotValue, UnresolvedSlot
from ambiguity_manager.schema.v2.taxonomies import RiskLevel
from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput


def load_resolution_policy(path: Path | None = None) -> dict[str, Any]:
  if path is None:
    path = ProjectPaths.from_repo_root().configs / "manager" / "context_resolution_policy_v1.json"
  return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class ResolutionEvent:
  slot: str
  previous_status: str
  outcome: str
  resolved_value: str | None
  evidence_source: str | None
  rule_id: str
  confidence_category: str
  safety_eligibility: bool
  details: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    return {
      "slot": self.slot,
      "previous_status": self.previous_status,
      "outcome": self.outcome,
      "resolved_value": self.resolved_value,
      "evidence_source": self.evidence_source,
      "rule_id": self.rule_id,
      "confidence_category": self.confidence_category,
      "safety_eligibility": self.safety_eligibility,
      "details": dict(self.details),
    }


@dataclass
class ResolutionResult:
  events: list[ResolutionEvent]
  resolved_slots: list[ResolvedSlotValue]
  unresolved_slots: list[UnresolvedSlot]
  resolution_evidence: list[EvidenceRef]
  resolution_method: str | None

  def to_dict(self) -> dict[str, Any]:
    return {
      "events": [e.to_dict() for e in self.events],
      "resolved_slots": [r.to_dict() for r in self.resolved_slots],
      "unresolved_slots": [u.to_dict() for u in self.unresolved_slots],
      "resolution_evidence": [e.to_dict() for e in self.resolution_evidence],
      "resolution_method": self.resolution_method,
    }


_REFERENT_RE = re.compile(r"(?:objects?|referents?)\s*[:=]\s*([^;\n]+)", re.IGNORECASE)
_DEST_RE = re.compile(r"(?:destinations?|locations?)\s*[:=]\s*([^;\n]+)", re.IGNORECASE)
_MENTION_RE = re.compile(r"(?:object|destination|tool)\s*[:=]\s*([A-Za-z0-9_\- ]+)", re.IGNORECASE)


def _split_values(blob: str) -> list[str]:
  parts = [p.strip() for p in re.split(r"[,|/]", blob) if p.strip()]
  return parts


class ContextResolver:
  def __init__(self, policy: dict[str, Any] | None = None) -> None:
    self.policy = policy or load_resolution_policy()

  def resolve(
    self,
    system_input: SystemInput,
    analysis: StructuredAnalysis,
    *,
    target_slots: list[str] | None = None,
  ) -> ResolutionResult:
    events: list[ResolutionEvent] = []
    resolved: list[ResolvedSlotValue] = list(analysis.resolved_slots)
    unresolved = list(analysis.unresolved_slots)
    evidence: list[EvidenceRef] = list(analysis.resolution_evidence)
    risk = analysis.risk_level
    block_levels = set(self.policy.get("block_silent_resolve_risk_levels", []))
    targets = target_slots or [u.slot_name for u in unresolved] or ["object", "destination"]

    if risk is not None and risk.value in block_levels and risk != RiskLevel.LOW:
      for slot in targets:
        events.append(
          ResolutionEvent(
            slot=slot,
            previous_status="unresolved",
            outcome="resolution_blocked_by_risk",
            resolved_value=None,
            evidence_source=None,
            rule_id="risk_block",
            confidence_category="blocked",
            safety_eligibility=False,
            details={"risk_level": risk.value},
          )
        )
      return ResolutionResult(
        events=events,
        resolved_slots=resolved,
        unresolved_slots=unresolved,
        resolution_evidence=evidence,
        resolution_method=None,
      )

    scene = system_input.scene_context or ""
    dialogue = " | ".join(system_input.dialogue_history)
    capability = system_input.capability_context or ""
    approved_defaults = self.policy.get("approved_defaults", {}) or {}

    for slot in targets:
      previous = "unresolved"
      if slot == "object":
        match = _REFERENT_RE.search(scene)
        if match:
          values = _split_values(match.group(1))
          if len(values) == 1:
            value = values[0]
            if value.lower() in system_input.command.lower() or True:
              events.append(
                ResolutionEvent(
                  slot=slot,
                  previous_status=previous,
                  outcome="resolved",
                  resolved_value=value,
                  evidence_source="scene_context",
                  rule_id="unique_scene_referent",
                  confidence_category="high",
                  safety_eligibility=True,
                )
              )
              resolved.append(ResolvedSlotValue(slot_name=slot, value=value))
              evidence.append(
                EvidenceRef(source="scene_context", span=value, note="unique_scene_referent")
              )
              unresolved = [u for u in unresolved if u.slot_name != slot]
              continue
          if len(values) > 1:
            events.append(
              ResolutionEvent(
                slot=slot,
                previous_status=previous,
                outcome="conflicting_context",
                resolved_value=None,
                evidence_source="scene_context",
                rule_id="unique_scene_referent",
                confidence_category="none",
                safety_eligibility=False,
                details={"candidates": values},
              )
            )
            continue
        # dialogue history
        mentions = _MENTION_RE.findall(dialogue)
        object_mentions = [m.strip() for m in mentions]
        if len(object_mentions) == 1:
          value = object_mentions[0]
          events.append(
            ResolutionEvent(
              slot=slot,
              previous_status=previous,
              outcome="resolved",
              resolved_value=value,
              evidence_source="dialogue_history",
              rule_id="dialogue_prior_mention",
              confidence_category="medium",
              safety_eligibility=True,
            )
          )
          resolved.append(ResolvedSlotValue(slot_name=slot, value=value))
          evidence.append(
            EvidenceRef(source="dialogue_history", span=value, note="dialogue_prior_mention")
          )
          unresolved = [u for u in unresolved if u.slot_name != slot]
          continue
        if slot in approved_defaults:
          value = str(approved_defaults[slot])
          events.append(
            ResolutionEvent(
              slot=slot,
              previous_status=previous,
              outcome="resolved",
              resolved_value=value,
              evidence_source="approved_default",
              rule_id="approved_default_only",
              confidence_category="policy",
              safety_eligibility=True,
            )
          )
          resolved.append(ResolvedSlotValue(slot_name=slot, value=value))
          evidence.append(
            EvidenceRef(source="approved_default", span=value, note="approved_default_only")
          )
          unresolved = [u for u in unresolved if u.slot_name != slot]
          continue
        events.append(
          ResolutionEvent(
            slot=slot,
            previous_status=previous,
            outcome="insufficient_context",
            resolved_value=None,
            evidence_source=None,
            rule_id="unique_scene_referent",
            confidence_category="none",
            safety_eligibility=False,
          )
        )
      elif slot == "destination":
        match = _DEST_RE.search(scene)
        if match:
          values = _split_values(match.group(1))
          if len(values) == 1:
            value = values[0]
            events.append(
              ResolutionEvent(
                slot=slot,
                previous_status=previous,
                outcome="resolved",
                resolved_value=value,
                evidence_source="scene_context",
                rule_id="unique_destination",
                confidence_category="high",
                safety_eligibility=True,
              )
            )
            resolved.append(ResolvedSlotValue(slot_name=slot, value=value))
            evidence.append(
              EvidenceRef(source="scene_context", span=value, note="unique_destination")
            )
            unresolved = [u for u in unresolved if u.slot_name != slot]
            continue
          if len(values) > 1:
            events.append(
              ResolutionEvent(
                slot=slot,
                previous_status=previous,
                outcome="conflicting_context",
                resolved_value=None,
                evidence_source="scene_context",
                rule_id="unique_destination",
                confidence_category="none",
                safety_eligibility=False,
                details={"candidates": values},
              )
            )
            continue
        events.append(
          ResolutionEvent(
            slot=slot,
            previous_status=previous,
            outcome="insufficient_context",
            resolved_value=None,
            evidence_source=None,
            rule_id="unique_destination",
            confidence_category="none",
            safety_eligibility=False,
          )
        )
      elif slot.startswith("capability") or slot == "tool":
        if capability.strip():
          events.append(
            ResolutionEvent(
              slot=slot,
              previous_status=previous,
              outcome="resolved" if ":" in capability else "insufficient_context",
              resolved_value=capability if ":" in capability else None,
              evidence_source="capability_context",
              rule_id="capability_lookup",
              confidence_category="medium",
              safety_eligibility=True,
            )
          )
          if ":" in capability:
            resolved.append(ResolvedSlotValue(slot_name=slot, value=capability))
            evidence.append(
              EvidenceRef(source="capability_context", span=capability, note="capability_lookup")
            )
            unresolved = [u for u in unresolved if u.slot_name != slot]
        else:
          events.append(
            ResolutionEvent(
              slot=slot,
              previous_status=previous,
              outcome="insufficient_context",
              resolved_value=None,
              evidence_source=None,
              rule_id="capability_lookup",
              confidence_category="none",
              safety_eligibility=False,
            )
          )
      else:
        if slot in approved_defaults:
          value = str(approved_defaults[slot])
          events.append(
            ResolutionEvent(
              slot=slot,
              previous_status=previous,
              outcome="resolved",
              resolved_value=value,
              evidence_source="approved_default",
              rule_id="approved_default_only",
              confidence_category="policy",
              safety_eligibility=True,
            )
          )
          resolved.append(ResolvedSlotValue(slot_name=slot, value=value))
          evidence.append(
            EvidenceRef(source="approved_default", span=value, note="approved_default_only")
          )
          unresolved = [u for u in unresolved if u.slot_name != slot]
        else:
          events.append(
            ResolutionEvent(
              slot=slot,
              previous_status=previous,
              outcome="unresolved",
              resolved_value=None,
              evidence_source=None,
              rule_id="no_world_knowledge_guess",
              confidence_category="none",
              safety_eligibility=False,
              details={"reason": "unsupported_default_rejected"},
            )
          )

    method = None
    if any(e.outcome == "resolved" for e in events):
      method = "deterministic_context_resolution_v1"
    return ResolutionResult(
      events=events,
      resolved_slots=resolved,
      unresolved_slots=unresolved,
      resolution_evidence=evidence,
      resolution_method=method,
    )

  def apply(self, analysis: StructuredAnalysis, result: ResolutionResult) -> StructuredAnalysis:
    analysis.resolved_slots = list(result.resolved_slots)
    analysis.unresolved_slots = list(result.unresolved_slots)
    analysis.resolution_evidence = list(result.resolution_evidence)
    analysis.resolution_method = result.resolution_method
    return analysis
