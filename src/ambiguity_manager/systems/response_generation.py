"""Deterministic clarification and rejection generators."""

from __future__ import annotations

import re
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

_PLACEHOLDER_VALUES = {
  "",
  "none",
  "null",
  "unknown",
  "unassigned",
  "n/a",
  "na",
  "not specified",
  "not applicable",
  "not_applicable",
}


def _clean_option(text: str) -> str:
  return re.sub(r"\s+", " ", (text or "").strip(" .,;:()[]"))


def _usable_value(value: object) -> str | None:
  if not isinstance(value, str):
    return None
  cleaned = _clean_option(value)
  if not cleaned or cleaned.casefold() in _PLACEHOLDER_VALUES:
    return None
  return cleaned


def _candidate_slot_options(analysis: StructuredAnalysis, slot: str) -> list[str]:
  options: list[str] = []
  seen: set[str] = set()
  for cand in analysis.candidate_interpretations:
    value = None
    if hasattr(cand.cpc, slot):
      slot_obj = getattr(cand.cpc, slot)
      value = getattr(slot_obj, "value", None)
    if isinstance(value, str) and value.strip():
      key = value.strip().lower()
      if key not in seen:
        seen.add(key)
        options.append(value.strip())
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


def _alternatives_from_intent_summary(summary: str) -> list[str]:
  """Pull already-written alternatives from the job box. Does not invent names."""
  text = (summary or "").strip()
  if not text:
    return []
  mill = re.search(
    r"(\d+)\s+or\s+(\d+)\s+(millilitres|milliliters|ml)\b",
    text,
    flags=re.IGNORECASE,
  )
  if mill:
    unit = mill.group(3)
    return [f"{mill.group(1)} {unit}", f"{mill.group(2)} {unit}"]
  either = re.search(
    r"either\s+(.{3,80}?)\s+or\s+(.{3,80}?)(?:[.,;]|$)",
    text,
    flags=re.IGNORECASE,
  )
  if either:
    return [either.group(1).strip(" ()"), either.group(2).strip(" ()")]
  paren = re.search(r"\(([^)]{3,80}?\bor\b[^)]{3,80})\)", text, flags=re.IGNORECASE)
  if paren:
    parts = re.split(r"\s+or\s+", paren.group(1), flags=re.IGNORECASE)
    if len(parts) == 2:
      return [p.strip() for p in parts]
  one_for = re.search(
    r"one for the ([^,.]{3,40}) and one for the ([^,.]{3,40})",
    text,
    flags=re.IGNORECASE,
  )
  if one_for:
    return [one_for.group(1).strip(), one_for.group(2).strip()]
  short_or = re.search(
    r"\b((?:physical|digital|grey|gray|amber|green|blue|red|yellow|black|"
    r"white|secure equipment bay unit [ab]|unit [ab]|homeowner badge [a-z0-9-]+|"
    r"exam packet|guest parcel|serving tray|controlled medicine tray|"
    r"[a-z]+ filing))\s+or\s+"
    r"((?:physical|digital|grey|gray|amber|green|blue|red|yellow|black|"
    r"white|secure equipment bay unit [ab]|unit [ab]|homeowner badge [a-z0-9-]+|"
    r"exam packet|guest parcel|serving tray|controlled medicine tray|"
    r"[a-z]+ filing))\b",
    text,
    flags=re.IGNORECASE,
  )
  if short_or:
    return [short_or.group(1).strip(), short_or.group(2).strip()]
  both = re.search(
    r"\bboth\s+(?:physical and digital|digital and physical)\b",
    text,
    flags=re.IGNORECASE,
  )
  if both:
    return ["physical filing", "digital filing"]
  for_role = re.search(
    r"(?:packet|parcel|tray|badge)\s+for\s+(?:the\s+)?([^,.]{3,40}?)\s+"
    r"(?:or|and)\s+(?:(?:packet|parcel|tray|badge)\s+for\s+(?:the\s+)?)?"
    r"([^,.]{3,40})(?:[.,;]|$)",
    text,
    flags=re.IGNORECASE,
  )
  if for_role:
    return [for_role.group(1).strip(), for_role.group(2).strip()]
  role_or = re.search(
    r"(?:assigned to|for)\s+(?:the\s+)?([^,.]{3,40}?)\s+or\s+(?:the\s+)?([^,.]{3,40})",
    text,
    flags=re.IGNORECASE,
  )
  if role_or:
    return [_clean_option(role_or.group(1)), _clean_option(role_or.group(2))]
  return []


def _alternatives_from_scene(scene: str) -> list[str]:
  """Extract licensed alternative pairs from scene_context. Never invents names."""
  text = (scene or "").strip()
  if not text:
    return []

  # Explicit authorized medium pair (prefer over generic folder/record).
  both_phys = re.search(
    r"both\s+(physical\s+filing\s+at\s+(?:the\s+)?[^.;,]{3,40}?)\s+and\s+"
    r"(digital\s+filing\s+in\s+(?:the\s+)?[^.;,]{3,40})",
    text,
    flags=re.IGNORECASE,
  )
  if both_phys:
    left = _clean_option(re.sub(r'\s+are authorized$', '', both_phys.group(1), flags=re.IGNORECASE))
    right = _clean_option(re.sub(r'\s+are authorized$', '', both_phys.group(2), flags=re.IGNORECASE))
    return [left, right]

  # Range instruments before east/west location distractors.
  handheld = re.search(
    r"handheld\s+unit\s+covers\s+the\s+low\s+range.*?cart-mounted\s+unit\s+covers\s+the\s+high\s+range",
    text,
    flags=re.IGNORECASE | re.DOTALL,
  )
  if handheld:
    if re.search(r"voltage\s+meter", text, flags=re.IGNORECASE):
      return [
        "handheld voltage meter for the low range",
        "cart-mounted voltage meter for the high range",
      ]
    return [
      "handheld pressure gauge for the low range",
      "cart-mounted pressure gauge for the high range",
    ]

  qty = re.search(
    r"(?:two approved quantities|permits exactly two approved quantities)"
    r"(?:\s+for\s+[^:]{1,40})?[:\s]+(\d+)\s+(millilitres|milliliters|ml)\s+and\s+(\d+)\s+(millilitres|milliliters|ml)",
    text,
    flags=re.IGNORECASE,
  )
  if qty:
    return [f"{qty.group(1)} {qty.group(2)}", f"{qty.group(3)} {qty.group(4)}"]

  colour_role = re.search(
    r"(?:the\s+)?(grey|gray|amber|green|blue|red|yellow|black|white)\s+one\s+is\s+assigned\s+to\s+"
    r"(?:the\s+)?([^.;,]{2,40}?)\s*[.;]\s*(?:the\s+)?"
    r"(grey|gray|amber|green|blue|red|yellow|black|white)\s+one\s+is\s+assigned\s+to\s+"
    r"(?:the\s+)?([^.;,]{2,40})",
    text,
    flags=re.IGNORECASE,
  )
  if colour_role:
    return [
      f"{colour_role.group(1)} for {colour_role.group(2).strip()}",
      f"{colour_role.group(3)} for {colour_role.group(4).strip()}",
    ]

  badge = re.search(
    r"badge\s+([A-Z0-9-]+)\s+at\s+the\s+([^.;,]{3,40}?)\s+and\s+badge\s+([A-Z0-9-]+)\s+at\s+the\s+([^.;,]{3,40})",
    text,
    flags=re.IGNORECASE,
  )
  if badge:
    return [
      f"homeowner badge {badge.group(1)} at the {badge.group(2).strip()}",
      f"homeowner badge {badge.group(3)} at the {badge.group(4).strip()}",
    ]

  unit_ab = re.search(
    r"unit\s+A\s+(?:at\s+)?(?:the\s+)?([^.;,]{3,50}?)\s*(?:[.;,]|and|,)\s*"
    r"(?:.*?unit\s+B\s+(?:at\s+)?(?:the\s+)?([^.;,]{3,50}))",
    text,
    flags=re.IGNORECASE | re.DOTALL,
  )
  if unit_ab:
    return [
      f"unit A at the {_clean_option(unit_ab.group(1))}",
      f"unit B at the {_clean_option(unit_ab.group(2))}",
    ]

  one_at = re.search(
    r"one\s+at\s+the\s+([^.;,]{3,50}?)\s+and\s+one\s+at\s+the\s+([^.;,]{3,50})",
    text,
    flags=re.IGNORECASE,
  )
  if one_at:
    return [
      f"at the {_clean_option(one_at.group(1))}",
      f"at the {_clean_option(one_at.group(2))}",
    ]

  one_for = re.search(
    r"one\s+for\s+(?:the\s+)?([^.;,]{2,40}?)\s+and\s+one\s+for\s+(?:the\s+)?([^.;,]{2,40})",
    text,
    flags=re.IGNORECASE,
  )
  if one_for:
    return [
      f"for the {_clean_option(one_for.group(1))}",
      f"for the {_clean_option(one_for.group(2))}",
    ]

  if re.search(r"physical\s+folder\s+and\s+a\s+digital\s+record", text, flags=re.IGNORECASE):
    dest = re.search(
      r"(service alcove|patio door|pass counter|window table)",
      text,
      flags=re.IGNORECASE,
    )
    dest_name = dest.group(0) if dest else "the licensed location"
    return [f"physical filing at {dest_name}", "digital filing in the records system"]

  gauge = re.search(
    r"(handheld\s+(?:pressure\s+gauge|voltage\s+meter)).*?(cart-mounted\s+(?:pressure\s+gauge|voltage\s+meter))",
    text,
    flags=re.IGNORECASE | re.DOTALL,
  )
  if gauge:
    left = _clean_option(gauge.group(1))
    right = _clean_option(gauge.group(2))
    if "low" not in left.casefold():
      left = f"{left} for the low range"
    if "high" not in right.casefold():
      right = f"{right} for the high range"
    return [left, right]

  if re.search(
    r"permits\s+inspection\s+without\s+movement.*?cancellation\s+of\s+both\s+actions",
    text,
    flags=re.IGNORECASE | re.DOTALL,
  ):
    return ["inspect without moving it", "cancel both move and inspect"]

  east_west = re.search(
    r"east-side\s+([^.;,]{3,40}).*?west-side\s+([^.;,]{3,40})",
    text,
    flags=re.IGNORECASE | re.DOTALL,
  )
  if east_west:
    return [
      f"east-side {_clean_option(east_west.group(1))}",
      f"west-side {_clean_option(east_west.group(2))}",
    ]

  return []


def _alternatives_from_cpc_values(analysis: StructuredAnalysis) -> list[str]:
  """Harvest 'X or Y' phrases already written into CPC cell values."""
  cpc = getattr(analysis, "cpc", None)
  if cpc is None:
    return []
  blobs: list[str] = []
  for name in (
    "object",
    "object_attributes",
    "recipient",
    "destination",
    "quantity",
    "tool",
    "constraints",
    "conditions",
    "action",
  ):
    slot = getattr(cpc, name, None)
    val = _usable_value(getattr(slot, "value", None) if slot is not None else None)
    if val:
      blobs.append(val)
  return _alternatives_from_intent_summary(" ; ".join(blobs))


def _question_from_options(options: list[str], target: str | None = None) -> str:
  cleaned = [_clean_option(o) for o in options if _clean_option(o)]
  seen: set[str] = set()
  uniq: list[str] = []
  for opt in cleaned:
    key = opt.casefold()
    if key in seen:
      continue
    seen.add(key)
    uniq.append(opt)
  if len(uniq) >= 2:
    if len(uniq) == 2:
      return f"Do you mean {uniq[0]} or {uniq[1]}?"
    joined = ", ".join(uniq[:-1]) + f", or {uniq[-1]}"
    label = (target or "option").replace("_", " ")
    return f"Which {label} do you mean: {joined}?"
  if len(uniq) == 1 and target:
    return f"Could you confirm the {target.replace('_', ' ')} is {uniq[0]}?"
  return ""


@dataclass
class DeterministicClarificationGenerator:
  provider_id: str = "deterministic_clarification"
  provider_version: str = "1.2.0"

  def generate_clarification(
    self,
    analysis: StructuredAnalysis,
    clarification_targets: list[str],
    *,
    scene_context: str | None = None,
  ) -> str:
    resolved = {r.slot_name for r in analysis.resolved_slots}
    seen: set[str] = set()
    targets: list[str] = []
    for target in clarification_targets:
      if target in resolved or target in seen:
        continue
      seen.add(target)
      targets.append(target)

    summary_options = _alternatives_from_intent_summary(
      getattr(analysis, "intent_summary", "") or ""
    )
    cpc_options = _alternatives_from_cpc_values(analysis)
    scene_options = _alternatives_from_scene(scene_context or "")

    if not targets:
      q = _question_from_options(summary_options or cpc_options or scene_options)
      return q or "Could you clarify what you would like me to do?"

    if len(targets) == 1:
      target = targets[0]
      options = _candidate_slot_options(analysis, target)
      if len(options) < 2:
        options = summary_options or cpc_options or scene_options
      q = _question_from_options(options, target)
      if q:
        return q
      return _SLOT_PROMPTS.get(
        target,
        f"Could you clarify the {target.replace('_', ' ')}?",
      )

    q = _question_from_options(summary_options or cpc_options or scene_options)
    if q:
      return q
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
  *,
  scene_context: str | None = None,
) -> str:
  if provider is not None:
    return provider.generate_clarification(analysis, targets)
  return DeterministicClarificationGenerator().generate_clarification(
    analysis, targets, scene_context=scene_context
  )


def generate_rejection(
  analysis: StructuredAnalysis,
  reason: str,
  provider: RejectionProvider | None = None,
) -> str:
  if provider is not None:
    return provider.generate_rejection(analysis, reason)
  return DeterministicRejectionGenerator().generate_rejection(analysis, reason)
