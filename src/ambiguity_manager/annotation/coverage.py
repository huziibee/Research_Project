"""Design-cell coverage reporting."""

from __future__ import annotations

from collections import Counter
from typing import Any

from ambiguity_manager.annotation.schema import load_design_cells
from ambiguity_manager.schema.v2.taxonomies import AmbiguityType, CapabilityStatus, RiskLevel, RouteLabel


def _speech_act_bucket(speech_act: str | None, design_cell: dict[str, Any]) -> str:
  if design_cell.get("speech_act_proxy") in {"direct", "indirect"}:
    return str(design_cell["speech_act_proxy"])
  if speech_act == "indirect_request":
    return "indirect"
  if speech_act in {None, "information_question", "other_non_actionable"}:
    return "other"
  return "direct"


def _context_bucket(record: dict[str, Any], design_cell: dict[str, Any]) -> str:
  if design_cell.get("context_proxy") in {"context_rich", "minimal_context"}:
    return str(design_cell["context_proxy"])
  scene = record.get("scene_context")
  dialogue = record.get("dialogue_history") or []
  if (isinstance(scene, str) and len(scene.strip()) >= 40) or len(dialogue) > 0:
    return "context_rich"
  return "minimal_context"


def _ambiguity_profile(design_cell: dict[str, Any]) -> str:
  profile = design_cell.get("ambiguity_profile")
  if profile:
    return str(profile)
  count = int(design_cell.get("compound_ambiguity_count", 0))
  if count <= 0:
    return "clear_no_ambiguity"
  if count == 1:
    return "single_ambiguity"
  if count == 2:
    return "compound_two_types"
  return "compound_three_or_more"


def summarise_coverage(records: list[dict[str, Any]]) -> dict[str, Any]:
  design = load_design_cells()
  profiles: Counter[str] = Counter()
  ambiguity_types: Counter[str] = Counter()
  risks: Counter[str] = Counter()
  strategies: Counter[str] = Counter()
  capabilities: Counter[str] = Counter()
  speech: Counter[str] = Counter()
  contexts: Counter[str] = Counter()
  safety_sensitive = 0

  for record in records:
    hidden = record.get("hidden") or {}
    cell = hidden.get("design_cell") or {}
    profiles[_ambiguity_profile(cell)] += 1
    for amb in cell.get("ambiguity_types") or []:
      ambiguity_types[str(amb)] += 1
    risk = cell.get("risk_level")
    strategy = cell.get("recommended_strategy")
    capability = cell.get("capability_status")
    if risk:
      risks[str(risk)] += 1
    if strategy:
      strategies[str(strategy)] += 1
    if capability:
      capabilities[str(capability)] += 1
    speech[_speech_act_bucket(cell.get("speech_act"), cell)] += 1
    contexts[_context_bucket(record, cell)] += 1
    if cell.get("safety_sensitive") or "safety_precondition" in (cell.get("ambiguity_types") or []) or risk == "high":
      safety_sensitive += 1

  def deficit(targets: dict[str, int], counts: Counter[str]) -> dict[str, int]:
    return {key: max(0, target - counts.get(key, 0)) for key, target in targets.items()}

  return {
    "n_records": len(records),
    "main_target_n": design["main_target_n"],
    "remaining_to_main_target": max(0, int(design["main_target_n"]) - len(records)),
    "counts": {
      "ambiguity_profile": dict(profiles),
      "ambiguity_types": dict(ambiguity_types),
      "risk_level": dict(risks),
      "recommended_strategy": dict(strategies),
      "capability_status": dict(capabilities),
      "speech_act_proxy": dict(speech),
      "context_proxy": dict(contexts),
      "safety_sensitive": safety_sensitive,
    },
    "deficits_vs_main_targets": {
      "ambiguity_profile": deficit(design["primary_ambiguity_profile"], profiles),
      "ambiguity_types": deficit(design["ambiguity_type_targets_among_ambiguous"], ambiguity_types),
      "risk_level": deficit(design["risk_targets"], risks),
      "recommended_strategy": deficit(design["strategy_targets"], strategies),
      "capability_status": deficit(design["capability_targets"], capabilities),
    },
    "calibration_presence_checks": {
      "all_routes": all(strategies.get(v.value, 0) > 0 for v in RouteLabel),
      "all_risks": all(risks.get(v.value, 0) > 0 for v in RiskLevel),
      "all_capabilities": all(capabilities.get(v.value, 0) > 0 for v in CapabilityStatus),
      "all_ambiguity_types": all(ambiguity_types.get(v.value, 0) > 0 for v in AmbiguityType),
      "has_clear": profiles.get("clear_no_ambiguity", 0) > 0,
      "has_single": profiles.get("single_ambiguity", 0) > 0,
      "has_compound": (
        profiles.get("compound_two_types", 0) + profiles.get("compound_three_or_more", 0)
      ) > 0,
      "has_direct": speech.get("direct", 0) > 0,
      "has_indirect": speech.get("indirect", 0) > 0,
      "has_context_rich": contexts.get("context_rich", 0) > 0,
      "has_minimal_context": contexts.get("minimal_context", 0) > 0,
      "has_safety_sensitive": safety_sensitive > 0,
    },
  }
