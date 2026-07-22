"""Model identity contract loader (T16-T24 model identity contract).

This module is the single source of truth for whether a base model, adapter,
or model strategy has been formally selected for official use. During T16-T24
every identity field must remain ``null``; no model has been selected and no
official model-backed run is permitted. See
``configs/model/selected_identities_v1.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.systems.errors import SystemsContractError

IDENTITY_FIELDS: tuple[str, ...] = (
  "selected_base_model",
  "selected_adapter",
  "selected_model_strategy",
)


@dataclass(frozen=True)
class SelectedIdentities:
  contract_id: str
  version: str
  selected_base_model: str | None
  selected_adapter: str | None
  selected_model_strategy: str | None
  status: str
  valid_for_official_use: bool

  def to_dict(self) -> dict[str, Any]:
    return {
      "contract_id": self.contract_id,
      "version": self.version,
      "selected_base_model": self.selected_base_model,
      "selected_adapter": self.selected_adapter,
      "selected_model_strategy": self.selected_model_strategy,
      "status": self.status,
      "valid_for_official_use": self.valid_for_official_use,
    }

  def is_null_selection(self) -> bool:
    return all(getattr(self, field) is None for field in IDENTITY_FIELDS)

  def assert_null_selection(self) -> None:
    """Raise if any identity field is populated.

    T16-T24 must never select a model, adapter, or strategy. Calling this
    guard at gate-evaluation time keeps that invariant enforced in code, not
    only in documentation.
    """
    populated = [field for field in IDENTITY_FIELDS if getattr(self, field) is not None]
    if populated:
      raise SystemsContractError(
        f"model identity contract expected null selection but found populated fields: {populated}"
      )
    if self.status != "no_selection":
      raise SystemsContractError(
        f"model identity contract status must be 'no_selection', found {self.status!r}"
      )
    if self.valid_for_official_use:
      raise SystemsContractError(
        "model identity contract must not be valid_for_official_use while selection is null"
      )


def _default_path() -> Path:
  return ProjectPaths.from_repo_root().configs / "model" / "selected_identities_v1.json"


def load_selected_identities(path: Path | None = None) -> SelectedIdentities:
  """Load and structurally validate the model identity contract."""
  resolved = path or _default_path()
  raw = json.loads(resolved.read_text(encoding="utf-8"))
  if not isinstance(raw, dict):
    raise SystemsContractError("selected_identities contract must be an object")
  missing = [key for key in ("contract_id", "version", "status") if key not in raw]
  if missing:
    raise SystemsContractError(f"selected_identities contract missing fields: {missing}")
  for field in IDENTITY_FIELDS:
    value = raw.get(field)
    if value is not None and not isinstance(value, str):
      raise SystemsContractError(f"{field} must be a string or null")
  return SelectedIdentities(
    contract_id=str(raw["contract_id"]),
    version=str(raw["version"]),
    selected_base_model=raw.get("selected_base_model"),
    selected_adapter=raw.get("selected_adapter"),
    selected_model_strategy=raw.get("selected_model_strategy"),
    status=str(raw.get("status", "unknown")),
    valid_for_official_use=bool(raw.get("valid_for_official_use", False)),
  )


def assert_null_selection(path: Path | None = None) -> SelectedIdentities:
  """Load the contract and assert every identity field is currently null."""
  identities = load_selected_identities(path)
  identities.assert_null_selection()
  return identities
