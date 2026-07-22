"""Deterministic clarification and rejection generators."""

from __future__ import annotations

from dataclasses import dataclass

from ambiguity_manager.systems.contracts import StructuredAnalysis
from ambiguity_manager.systems.providers import ClarificationProvider, RejectionProvider


_SLOT_PROMPTS: dict[str, str] = {
  "object": "Which object do you mean?",
  "destination": "Could you clarify the destination?",
  "spatial_relation": "Could you clarify the spatial relation?",
  "tool": "Which tool should I use?",
  "quantity": "How many should I handle?",
  "time": "When should I do that?",
  "action": "Which action should I perform?",
  "conditions": "Which condition should I follow?",
  "constraints": "Which constraint should I respect?",
  "recipient": "Who is the recipient?",
  "referential": "Which referent do you mean?",
  "safety_precondition": "Before I continue, which item is safe to handle?",
  "capability": "Could you clarify the required capability?",
  "risk": "Could you clarify the safety constraint?",
  "intent": "Could you clarify what you would like me to do?",
}


def _candidate_slot_options(analysis: StructuredAnalysis, slot: str) -> list[str]:
  options: list[str] = []
  seen: set[str] = set()
  for cand in analysis.candidate_interpretations:
    value = None
    if hasattr(cand.cpc, slot):
      slot_obj = getattr(cand.cpc, slot)
      value = getattr(slot_obj, "value", None)
    if not value and cand.text:
      # Fall back only to explicit candidate text differences when slot empty.
      value = None
    if isinstance(value, str) and value.strip():
      key = value.strip().lower()
      if key not in seen:
        seen.add(key)
        options.append(value.strip())
  # Also derive from distinct candidate texts when slot-level values absent.
  if not options:
    texts = []
    for cand in analysis.candidate_interpretations:
      if cand.text and cand.text.strip():
        key = cand.text.strip().lower()
        if key not in seen:
          seen.add(key)
          texts.append(cand.text.strip())
    if len(texts) >= 2:
      options = texts
  return options


@dataclass
class DeterministicClarificationGenerator:
  provider_id: str = "deterministic_clarification"
  provider_version: str = "1.0.0"

  def generate_clarification(
    self,
    analysis: StructuredAnalysis,
    clarification_targets: list[str],
  ) -> str:
    # Preserve order, drop duplicates and already-resolved slots.
    resolved = {r.slot_name for r in analysis.resolved_slots}
    seen: set[str] = set()
    targets: list[str] = []
    for target in clarification_targets:
      if target in resolved:
        continue
      if target in seen:
        continue
      seen.add(target)
      targets.append(target)
    if not targets:
      return "Could you clarify what you would like me to do?"
    if len(targets) == 1:
      target = targets[0]
      options = _candidate_slot_options(analysis, target)
      if len(options) >= 2:
        # Grounded alternatives only from actual candidate differences.
        if len(options) == 2:
          return f"Do you mean {options[0]} or {options[1]}?"
        joined = ", ".join(options[:-1]) + f", or {options[-1]}"
        return f"Which {target.replace('_', ' ')} do you mean: {joined}?"
      if len(options) == 1:
        return (
          f"Could you confirm the {target.replace('_', ' ')} is {options[0]}?"
        )
      # No grounded alternatives — open slot-specific question.
      return _SLOT_PROMPTS.get(
        target,
        f"Could you clarify the {target.replace('_', ' ')}?",
      )
    # Multi-target: concise grounded prompt without inventing entities.
    pretty = ", ".join(t.replace("_", " ") for t in targets)
    return f"Before I continue, could you clarify: {pretty}?"


@dataclass
class DeterministicRejectionGenerator:
  provider_id: str = "deterministic_rejection"
  provider_version: str = "1.0.0"

  def generate_rejection(
    self,
    analysis: StructuredAnalysis,
    rejection_reason: str,
  ) -> str:
    reason = rejection_reason or analysis.rejection_reason or "constraint"
    templates = {
      "known_incapability": (
        "I am not able to perform that action with my current capabilities. "
        "I will not invent an alternative that is not supported."
      ),
      "unsafe_or_prohibited_action": (
        "I need to decline that request because it would be unsafe under the current constraints."
      ),
      "unavailable_tool": (
        "I do not have the required tool available, so I cannot complete that request right now."
      ),
      "conditional_capability": (
        "I can only proceed if the required safety conditions are met, which they are not yet."
      ),
      "capability_limitation": (
        "I am limited in what I can do here and cannot complete that request as stated."
      ),
      "safety_prohibition": (
        "I need to decline for safety reasons and will not proceed with that action."
      ),
    }
    text = templates.get(reason)
    if text is None:
      text = (
        "I need to decline that request because of a verified limitation or safety concern. "
        "I will not pretend that I can complete it."
      )
    return text


def generate_clarification(
  analysis: StructuredAnalysis,
  targets: list[str],
  provider: ClarificationProvider | None = None,
) -> str:
  if provider is not None:
    return provider.generate_clarification(analysis, targets)
  return DeterministicClarificationGenerator().generate_clarification(analysis, targets)


def generate_rejection(
  analysis: StructuredAnalysis,
  reason: str,
  provider: RejectionProvider | None = None,
) -> str:
  if provider is not None:
    return provider.generate_rejection(analysis, reason)
  return DeterministicRejectionGenerator().generate_rejection(analysis, reason)
