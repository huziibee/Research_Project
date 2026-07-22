"""System capability registry.

Declares, per comparison system, the structural requirements that govern
whether it may run in a given ``run_mode`` and what it needs to be eligible
for *official* execution. ``execution.py`` must derive its official-mode
gating from this registry rather than hard-coding system-id string checks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.systems.errors import SystemsContractError

_BOOL_FIELDS: tuple[str, ...] = (
  "requires_structured_analysis",
  "can_use_supplied_cached_analysis",
  "requires_live_model_provider",
  "requires_approved_analysis_provenance_in_official_mode",
  "requires_selected_base_model",
  "requires_selected_adapter",
  "requires_selected_model_strategy",
  "forbids_selected_adapter",
  "allows_full_context_cache",
)

_DEFAULT_RUN_MODES: tuple[str, ...] = ("synthetic_smoke", "development", "official")


@dataclass(frozen=True)
class SystemCapabilities:
  system_id: str
  requires_structured_analysis: bool = False
  can_use_supplied_cached_analysis: bool = False
  requires_live_model_provider: bool = False
  requires_approved_analysis_provenance_in_official_mode: bool = False
  requires_selected_base_model: bool = False
  requires_selected_adapter: bool = False
  requires_selected_model_strategy: bool = False
  forbids_selected_adapter: bool = False
  allows_full_context_cache: bool = True
  allowed_run_modes: tuple[str, ...] = field(default_factory=lambda: _DEFAULT_RUN_MODES)

  def to_dict(self) -> dict[str, Any]:
    payload: dict[str, Any] = {"system_id": self.system_id}
    for name in _BOOL_FIELDS:
      payload[name] = getattr(self, name)
    payload["allowed_run_modes"] = list(self.allowed_run_modes)
    return payload

  @classmethod
  def from_dict(cls, system_id: str, data: dict[str, Any]) -> "SystemCapabilities":
    if not isinstance(data, dict):
      raise SystemsContractError(f"capabilities for {system_id!r} must be an object")
    kwargs: dict[str, Any] = {name: bool(data.get(name, False)) for name in _BOOL_FIELDS}
    kwargs["allows_full_context_cache"] = bool(data.get("allows_full_context_cache", True))
    modes = data.get("allowed_run_modes")
    if modes is None:
      modes = list(_DEFAULT_RUN_MODES)
    if not isinstance(modes, list) or not all(isinstance(m, str) for m in modes):
      raise SystemsContractError(f"allowed_run_modes for {system_id!r} must be a list of strings")
    return cls(system_id=system_id, allowed_run_modes=tuple(modes), **kwargs)

  def allows_run_mode(self, run_mode: str) -> bool:
    return run_mode in self.allowed_run_modes


def _default_path() -> Path:
  return ProjectPaths.from_repo_root().configs / "manager" / "system_variants_v1.json"


def load_capability_registry(path: Path | None = None) -> dict[str, SystemCapabilities]:
  """Load the per-system capability registry from ``system_variants_v1.json``."""
  resolved = path or _default_path()
  raw = json.loads(resolved.read_text(encoding="utf-8"))
  systems = raw.get("systems")
  if not isinstance(systems, list):
    raise SystemsContractError("system_variants config must contain a 'systems' list")
  registry: dict[str, SystemCapabilities] = {}
  for entry in systems:
    if not isinstance(entry, dict) or "system_id" not in entry:
      raise SystemsContractError("each system entry requires a system_id")
    system_id = str(entry["system_id"])
    registry[system_id] = SystemCapabilities.from_dict(system_id, entry)
  return registry


def is_provenance_approved(analysis_provenance: Any) -> bool:
  """Return True only when analysis provenance is explicitly marked approved.

  No approval workflow exists yet in T16-T24, so this always evaluates to
  False against current fixtures/providers. That is intentional: official-mode
  use of cached or provider-supplied structured analysis stays blocked until
  an approval mechanism is built and providers are updated to set it.
  """
  method = getattr(analysis_provenance, "method", None)
  return method == "approved"
