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


_OBJECT_RE = re.compile(r"(?:^|[;\n])\s*objects?\s*[:=]\s*([^;\n]+)", re.IGNORECASE)
_DEST_RE = re.compile(r"(?:^|[;\n])\s*destinations?\s*[:=]\s*([^;\n]+)", re.IGNORECASE)
_TOOL_RE = re.compile(r"(?:^|[;\n])\s*tools?\s*[:=]\s*([^;\n]+)", re.IGNORECASE)
_OBJECT_MENTION_RE = re.compile(r"(?:^|[|;])\s*object\s*[:=]\s*([^|;]+)", re.IGNORECASE)
_DEST_MENTION_RE = re.compile(r"(?:^|[|;])\s*destination\s*[:=]\s*([^|;]+)", re.IGNORECASE)
_TOOL_MENTION_RE = re.compile(r"(?:^|[|;])\s*tool\s*[:=]\s*([^|;]+)", re.IGNORECASE)


def _split_values(blob: str) -> list[str]:
  return [p.strip() for p in re.split(r"[,|/]", blob) if p.strip()]


def _command_compatible(value: str, command: str) -> bool:
  """Require token overlap between candidate value and command (no unconditional bypass)."""
  cmd = command.lower()
  val = value.lower().strip()
  if not val:
    return False
  if val in cmd:
    return True
  tokens = [t for t in re.split(r"\s+", val) if len(t) > 2]
  if not tokens:
    return val in cmd
  return any(t in cmd for t in tokens)


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
    already_filled = {r.slot_name: r for r in resolved}

    # Only process explicitly unresolved / resolution-eligible slots.
    if target_slots is not None:
      targets = list(target_slots)
    else:
      targets = [u.slot_name for u in unresolved]
    # De-duplicate targets while preserving order.
    seen_targets: set[str] = set()
    ordered_targets: list[str] = []
    for slot in targets:
      if slot in seen_targets:
        continue
      seen_targets.add(slot)
      ordered_targets.append(slot)
    targets = ordered_targets

    if not targets:
      return ResolutionResult(
        events=events,
        resolved_slots=resolved,
        unresolved_slots=unresolved,
        resolution_evidence=evidence,
        resolution_method=None,
      )

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

    def _record_resolved(
      slot: str,
      value: str,
      *,
      source: str,
      rule_id: str,
      confidence: str,
    ) -> None:
      nonlocal unresolved
      if slot in already_filled:
        existing = already_filled[slot]
        if existing.value != value:
          events.append(
            ResolutionEvent(
              slot=slot,
              previous_status="filled",
              outcome="conflicting_context",
              resolved_value=None,
              evidence_source=source,
              rule_id=rule_id,
              confidence_category="none",
              safety_eligibility=False,
              details={
                "existing_value": existing.value,
                "candidate_value": value,
                "reason": "refusing_overwrite_of_supported_value",
              },
            )
          )
        else:
          events.append(
            ResolutionEvent(
              slot=slot,
              previous_status="filled",
              outcome="already_resolved",
              resolved_value=existing.value,
              evidence_source=source,
              rule_id=rule_id,
              confidence_category=confidence,
              safety_eligibility=True,
              details={"reason": "duplicate_resolution_suppressed"},
            )
          )
        return
      if any(r.slot_name == slot for r in resolved):
        events.append(
          ResolutionEvent(
            slot=slot,
            previous_status="resolved",
            outcome="duplicate_suppressed",
            resolved_value=value,
            evidence_source=source,
            rule_id=rule_id,
            confidence_category="none",
            safety_eligibility=False,
          )
        )
        return
      events.append(
        ResolutionEvent(
          slot=slot,
          previous_status="unresolved",
          outcome="resolved",
          resolved_value=value,
          evidence_source=source,
          rule_id=rule_id,
          confidence_category=confidence,
          safety_eligibility=True,
        )
      )
      item = ResolvedSlotValue(slot_name=slot, value=value)
      resolved.append(item)
      already_filled[slot] = item
      evidence.append(EvidenceRef(source=source, span=value, note=rule_id))
      unresolved = [u for u in unresolved if u.slot_name != slot]

    for slot in targets:
      if slot == "object":
        match = _OBJECT_RE.search(scene)
        if match:
          values = _split_values(match.group(1))
          if len(values) == 1:
            value = values[0]
            if _command_compatible(value, system_input.command):
              _record_resolved(
                slot,
                value,
                source="scene_context",
                rule_id="unique_scene_referent",
                confidence="high",
              )
              continue
            events.append(
              ResolutionEvent(
                slot=slot,
                previous_status="unresolved",
                outcome="incompatible_command_context",
                resolved_value=None,
                evidence_source="scene_context",
                rule_id="unique_scene_referent",
                confidence_category="none",
                safety_eligibility=False,
                details={"value": value},
              )
            )
            continue
          if len(values) > 1:
            events.append(
              ResolutionEvent(
                slot=slot,
                previous_status="unresolved",
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
        object_mentions = [m.strip() for m in _OBJECT_MENTION_RE.findall(dialogue)]
        if len(object_mentions) == 1:
          _record_resolved(
            slot,
            object_mentions[0],
            source="dialogue_history",
            rule_id="dialogue_prior_mention",
            confidence="medium",
          )
          continue
        if len(object_mentions) > 1:
          events.append(
            ResolutionEvent(
              slot=slot,
              previous_status="unresolved",
              outcome="conflicting_context",
              resolved_value=None,
              evidence_source="dialogue_history",
              rule_id="dialogue_prior_mention",
              confidence_category="none",
              safety_eligibility=False,
              details={"candidates": object_mentions},
            )
          )
          continue
        if slot in approved_defaults:
          _record_resolved(
            slot,
            str(approved_defaults[slot]),
            source="approved_default",
            rule_id="approved_default_only",
            confidence="policy",
          )
          continue
        events.append(
          ResolutionEvent(
            slot=slot,
            previous_status="unresolved",
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
            cmd_l = system_input.command.lower()
            implies_destination = any(
              tok in cmd_l
              for tok in (
                "there",
                "that",
                "here",
                "put",
                "place",
                "bring",
                "move",
                "take",
                "set",
                "table",
                "counter",
                "shelf",
              )
            )
            if _command_compatible(value, system_input.command) or implies_destination:
              _record_resolved(
                slot,
                value,
                source="scene_context",
                rule_id="unique_destination",
                confidence="high",
              )
              continue
            events.append(
              ResolutionEvent(
                slot=slot,
                previous_status="unresolved",
                outcome="incompatible_command_context",
                resolved_value=None,
                evidence_source="scene_context",
                rule_id="unique_destination",
                confidence_category="none",
                safety_eligibility=False,
                details={"value": value},
              )
            )
            continue
          if len(values) > 1:
            events.append(
              ResolutionEvent(
                slot=slot,
                previous_status="unresolved",
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
        dest_mentions = [m.strip() for m in _DEST_MENTION_RE.findall(dialogue)]
        if len(dest_mentions) == 1:
          _record_resolved(
            slot,
            dest_mentions[0],
            source="dialogue_history",
            rule_id="dialogue_prior_mention",
            confidence="medium",
          )
          continue
        events.append(
          ResolutionEvent(
            slot=slot,
            previous_status="unresolved",
            outcome="insufficient_context",
            resolved_value=None,
            evidence_source=None,
            rule_id="unique_destination",
            confidence_category="none",
            safety_eligibility=False,
          )
        )
      elif slot == "tool" or slot.startswith("capability"):
        tool_match = _TOOL_RE.search(capability) or _TOOL_MENTION_RE.search(capability)
        if tool_match:
          values = _split_values(tool_match.group(1))
          if len(values) == 1:
            _record_resolved(
              slot,
              values[0],
              source="capability_context",
              rule_id="capability_lookup",
              confidence="medium",
            )
            continue
          events.append(
            ResolutionEvent(
              slot=slot,
              previous_status="unresolved",
              outcome="conflicting_context",
              resolved_value=None,
              evidence_source="capability_context",
              rule_id="capability_lookup",
              confidence_category="none",
              safety_eligibility=False,
              details={"candidates": values},
            )
          )
          continue
        events.append(
          ResolutionEvent(
            slot=slot,
            previous_status="unresolved",
            outcome="insufficient_context",
            resolved_value=None,
            evidence_source=None,
            rule_id="capability_lookup",
            confidence_category="none",
            safety_eligibility=False,
            details={"reason": "refusing_raw_capability_string_as_tool_value"},
          )
        )
      else:
        if slot in approved_defaults:
          _record_resolved(
            slot,
            str(approved_defaults[slot]),
            source="approved_default",
            rule_id="approved_default_only",
            confidence="policy",
          )
        else:
          events.append(
            ResolutionEvent(
              slot=slot,
              previous_status="unresolved",
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
    # Operate on an isolated working copy; callers may pass shared analysis.
    from ambiguity_manager.systems.analysis import analysis_from_cached

    working = analysis_from_cached(analysis)
    working.resolved_slots = list(result.resolved_slots)
    working.unresolved_slots = list(result.unresolved_slots)
    working.resolution_evidence = list(result.resolution_evidence)
    working.resolution_method = result.resolution_method
    return working
