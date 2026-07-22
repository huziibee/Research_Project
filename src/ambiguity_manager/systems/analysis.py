"""Shared analysis helpers for systems package."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from ambiguity_manager.schema.v2.records import UnresolvedSlot
from ambiguity_manager.systems.contracts import AnalysisProvenance, StructuredAnalysis, SystemInput
from ambiguity_manager.systems.errors import ContextAblationError
from ambiguity_manager.systems.hashing import sha256_json

_CONTEXT_SOURCES = frozenset({"scene_context", "dialogue_history", "capability_context"})
ANALYSIS_VARIANTS = frozenset({"full_context", "context_blind"})


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


@dataclass(frozen=True)
class AnalysisIdentity:
  """Canonical identity for a cached or freshly produced structured analysis.

  Distinguishes full-context vs context-blind analyses even when they share a
  record_id. The source_input_hash must be the fingerprint of the SystemInput
  actually analysed (ablated for context-blind).
  """

  record_id: str
  source_input_hash: str
  analysis_variant: str
  provider_id: str | None
  provider_version: str | None
  model_strategy_id: str | None
  analysis_content_hash: str

  def to_dict(self) -> dict[str, Any]:
    return {
      "record_id": self.record_id,
      "source_input_hash": self.source_input_hash,
      "analysis_variant": self.analysis_variant,
      "provider_id": self.provider_id,
      "provider_version": self.provider_version,
      "model_strategy_id": self.model_strategy_id,
      "analysis_content_hash": self.analysis_content_hash,
    }

  def fingerprint(self) -> str:
    return sha256_json(self.to_dict())


def build_analysis_identity(
  *,
  record_id: str,
  source_input: SystemInput,
  analysis: StructuredAnalysis,
  analysis_variant: str,
  model_strategy_id: str | None = None,
) -> AnalysisIdentity:
  if analysis_variant not in ANALYSIS_VARIANTS:
    raise ValueError(f"unknown analysis_variant: {analysis_variant}")
  prov = analysis.analysis_provenance
  return AnalysisIdentity(
    record_id=record_id,
    source_input_hash=source_input.fingerprint(),
    analysis_variant=analysis_variant,
    provider_id=prov.provider_id if prov else None,
    provider_version=prov.provider_version if prov else None,
    model_strategy_id=model_strategy_id,
    analysis_content_hash=analysis.fingerprint(),
  )


def strip_context_dependent_fields(analysis: StructuredAnalysis) -> StructuredAnalysis:
  """Remove resolutions and evidence that depended on dialogue/scene/capability context.

  Retained only for diagnostics/legacy callers. Context-blind execution must
  never use this as a fallback to sanitise a full-context cached analysis.
  """
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


def _extract_recorded_input_hash(prov: AnalysisProvenance | None) -> str | None:
  if prov is None:
    return None
  notes = prov.notes or ""
  for key in ("ablated_input_hash=", "source_input_hash=", "ablation_input_hash="):
    if key in notes:
      return notes.split(key, 1)[1].split(";", 1)[0].strip() or None
  if prov.analysis_id and len(prov.analysis_id) >= 16:
    return prov.analysis_id
  return None


def is_context_blind_provenance(prov: AnalysisProvenance | None) -> bool:
  return _explicit_context_blind_provenance(prov)


def _explicit_context_blind_provenance(prov: AnalysisProvenance | None) -> bool:
  if prov is None:
    return False
  notes = (prov.notes or "").lower()
  method = (prov.method or "").lower()
  provider_id = (prov.provider_id or "").lower()
  return (
    "context_blind" in notes
    or method == "context_blind"
    or provider_id.endswith("context_blind")
    or "context_blind" in provider_id
  )


def validate_context_blind_cache(
  cached: StructuredAnalysis,
  *,
  ablated_input: SystemInput,
) -> StructuredAnalysis:
  """Accept a cached analysis only when it is explicitly context-blind and matches.

  A matching cache is accepted as-is (deep-copied). Full-context analyses are
  never sanitised for reuse — callers must obtain a fresh ablated analysis or
  a genuine context-blind cache instead.
  """
  prov = cached.analysis_provenance
  expected_hash = ablated_input.fingerprint()
  recorded_hash = _extract_recorded_input_hash(prov)

  if not _explicit_context_blind_provenance(prov):
    raise ContextAblationError(
      "context-blind system rejects full-context cached analysis; "
      "require fresh analysis or provenance explicitly stating context_blind"
    )
  if recorded_hash is None:
    raise ContextAblationError(
      "context-blind cached analysis is missing ablated/source input hash in provenance"
    )
  if recorded_hash != expected_hash:
    raise ContextAblationError(
      "context-blind cached analysis input hash does not match ablated SystemInput"
    )

  working = copy.deepcopy(cached)
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
