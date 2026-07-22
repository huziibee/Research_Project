"""Shared analysis helpers for systems package."""

from __future__ import annotations

import copy

from ambiguity_manager.schema.v2.records import UnresolvedSlot
from ambiguity_manager.systems.contracts import AnalysisProvenance, StructuredAnalysis, SystemInput
from ambiguity_manager.systems.errors import ContextAblationError
from ambiguity_manager.systems.hashing import sha256_json

_CONTEXT_SOURCES = frozenset({"scene_context", "dialogue_history", "capability_context"})


def analysis_from_cached(
  cached: StructuredAnalysis,
  *,
  mutate: bool = False,
) -> StructuredAnalysis:
  """Return a copy of cached analysis unless mutate is explicitly requested."""
  if mutate:
    return cached
  return copy.deepcopy(cached)


def ensure_input_not_mutated(original: SystemInput, current: SystemInput) -> None:
  if original.to_dict() != current.to_dict():
    raise AssertionError("SystemInput was mutated")


def strip_context_dependent_fields(analysis: StructuredAnalysis) -> StructuredAnalysis:
  """Remove resolutions and evidence that depended on dialogue/scene/capability context."""
  working = copy.deepcopy(analysis)
  context_evidence = [
    e for e in working.resolution_evidence if (e.source or "") in _CONTEXT_SOURCES
  ]
  context_values = {(e.span or "").strip().lower() for e in context_evidence if e.span}
  context_notes = " ".join((e.note or "") for e in context_evidence)

  filtered_resolved = []
  removed_slots: list[str] = []
  for item in working.resolved_slots:
    value_key = (item.value or "").strip().lower()
    linked_context = any(
      (e.source or "") in _CONTEXT_SOURCES
      and (
        (e.span or "").strip().lower() == value_key
        or item.slot_name in (e.note or "")
        or item.slot_name in context_notes
      )
      for e in working.resolution_evidence
    )
    if linked_context or (value_key and value_key in context_values):
      removed_slots.append(item.slot_name)
      continue
    # If the only resolution evidence is contextual, drop all prior context resolutions.
    if context_evidence and not any(
      (e.source or "") not in _CONTEXT_SOURCES
      and (e.span or "").strip().lower() == value_key
      for e in working.resolution_evidence
    ):
      # Keep values that have independent non-context support only.
      if value_key in context_values or item.slot_name in {
        e.note for e in context_evidence if e.note
      }:
        removed_slots.append(item.slot_name)
        continue
    filtered_resolved.append(item)

  # Stronger rule: any resolved slot that appears in context-sourced evidence is removed.
  if context_evidence:
    strong_removed = []
    strong_kept = []
    for item in working.resolved_slots:
      value_key = (item.value or "").strip().lower()
      if any(
        (e.source or "") in _CONTEXT_SOURCES
        and (
          (e.span or "").strip().lower() == value_key
          or item.slot_name in (e.note or "")
        )
        for e in working.resolution_evidence
      ):
        strong_removed.append(item.slot_name)
      else:
        # Also remove if evidence list is exclusively contextual for this analysis.
        if all((e.source or "") in _CONTEXT_SOURCES for e in working.resolution_evidence):
          strong_removed.append(item.slot_name)
        else:
          strong_kept.append(item)
    filtered_resolved = strong_kept
    removed_slots = strong_removed

  working.resolved_slots = filtered_resolved
  working.resolution_evidence = [
    e for e in working.resolution_evidence if (e.source or "") not in _CONTEXT_SOURCES
  ]
  existing_unresolved = {u.slot_name for u in working.unresolved_slots}
  for slot in removed_slots:
    if slot not in existing_unresolved:
      working.unresolved_slots.append(
        UnresolvedSlot(slot_name=slot, reason="context_ablation_removed_resolution")
      )
      existing_unresolved.add(slot)
  if removed_slots:
    working.resolution_method = None
    working.findings = list(working.findings) + [
      f"context_ablation_stripped:{','.join(sorted(set(removed_slots)))}"
    ]
  return working


def validate_context_blind_cache(
  cached: StructuredAnalysis,
  *,
  ablated_input: SystemInput,
) -> StructuredAnalysis:
  """Accept a cached analysis only when provenance explicitly states context_blind."""
  prov = cached.analysis_provenance
  notes = (prov.notes or "") if prov else ""
  method = (prov.method or "") if prov else ""
  provider_id = (prov.provider_id or "") if prov else ""
  explicit_blind = (
    "context_blind" in notes.lower()
    or method.lower() == "context_blind"
    or provider_id.endswith("context_blind")
    or "context_blind" in provider_id
  )
  expected_hash = ablated_input.fingerprint()
  recorded_hash = None
  for key in ("ablated_input_hash=", "ablation_input_hash="):
    if key in notes:
      recorded_hash = notes.split(key, 1)[1].split(";", 1)[0].strip()
      break
  if recorded_hash is None and prov and prov.analysis_id and len(prov.analysis_id) >= 16:
    recorded_hash = prov.analysis_id

  if not explicit_blind:
    raise ContextAblationError(
      "context-blind system rejects full-context cached analysis; "
      "require fresh analysis or provenance explicitly stating context_blind"
    )
  if recorded_hash is not None and recorded_hash != expected_hash:
    raise ContextAblationError(
      "context-blind cached analysis input hash does not match ablated SystemInput"
    )
  working = strip_context_dependent_fields(cached)
  working.analysis_provenance = AnalysisProvenance(
    provider_id=prov.provider_id if prov else "context_blind_cache",
    provider_version=prov.provider_version if prov else "1.0.0",
    analysis_id=expected_hash,
    method="context_blind",
    notes=f"ablated_input_hash={expected_hash};accepted_context_blind_cache",
  )
  return working


def attach_ablation_provenance(
  analysis: StructuredAnalysis,
  *,
  ablated_input: SystemInput,
) -> StructuredAnalysis:
  working = copy.deepcopy(analysis)
  digest = ablated_input.fingerprint()
  prev = working.analysis_provenance
  working.analysis_provenance = AnalysisProvenance(
    provider_id=prev.provider_id,
    provider_version=prev.provider_version,
    analysis_id=digest,
    method="context_blind",
    notes=f"ablated_input_hash={digest};{(prev.notes or '')}".strip(";"),
  )
  return working


def canonical_analysis_identity(analysis: StructuredAnalysis) -> str:
  return sha256_json(analysis.to_dict())
