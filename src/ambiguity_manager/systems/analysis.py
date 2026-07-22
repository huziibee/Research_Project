"""Shared analysis helpers for systems package."""

from __future__ import annotations

import copy

from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput


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
