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

CHECKPOINT_IDENTITY_SEPARATOR = "@"


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
    only in documentation. ``no_viable_base_candidate`` is an allowed null
    status after a failed development bake-off.
    """
    populated = [field for field in IDENTITY_FIELDS if getattr(self, field) is not None]
    if populated:
      raise SystemsContractError(
        f"model identity contract expected null selection but found populated fields: {populated}"
      )
    if self.status not in {"no_selection", "no_viable_base_candidate"}:
      raise SystemsContractError(
        "model identity contract status must be 'no_selection' or "
        f"'no_viable_base_candidate', found {self.status!r}"
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


def checkpoint_identity(repository: str, revision: str) -> str:
  """Format an immutable checkpoint identity used by selected_base_model."""
  repo = repository.strip()
  rev = revision.strip()
  if not repo or not rev:
    raise SystemsContractError("checkpoint identity requires non-empty repository and revision")
  if CHECKPOINT_IDENTITY_SEPARATOR in rev:
    raise SystemsContractError("revision must not contain the checkpoint identity separator")
  return f"{repo}{CHECKPOINT_IDENTITY_SEPARATOR}{rev}"


def parse_checkpoint_identity(identity: str) -> tuple[str, str]:
  """Split a checkpoint identity into repository and revision."""
  if CHECKPOINT_IDENTITY_SEPARATOR not in identity:
    raise SystemsContractError(f"invalid checkpoint identity: {identity!r}")
  repository, revision = identity.rsplit(CHECKPOINT_IDENTITY_SEPARATOR, 1)
  if not repository or not revision:
    raise SystemsContractError(f"invalid checkpoint identity: {identity!r}")
  return repository, revision


def assert_adapter_matches_selected_base(
  *,
  selected_base_model: str | None,
  adapter_base_model: str | None,
) -> None:
  """An adapter must declare the same base checkpoint as selected_base_model."""
  if selected_base_model is None:
    raise SystemsContractError(
      "adapter registration requires a selected_base_model before adapter identity can be validated"
    )
  if adapter_base_model is None:
    raise SystemsContractError("adapter registration must declare adapter_base_model")
  if adapter_base_model != selected_base_model:
    raise SystemsContractError(
      "adapter base-model identity must match selected_base_model "
      f"(expected {selected_base_model!r}, got {adapter_base_model!r})"
    )


def assert_adapter_cannot_mutate_base_identity(
  *,
  original_selected_base_model: str,
  proposed_selected_base_model: str | None,
) -> None:
  """Adapter registration must not rewrite the selected base checkpoint."""
  if proposed_selected_base_model != original_selected_base_model:
    raise SystemsContractError(
      "adapter registration cannot mutate selected_base_model "
      f"(expected {original_selected_base_model!r}, got {proposed_selected_base_model!r})"
    )


def assert_strategy_requires_selected_base(*, selected_base_model: str | None) -> None:
  """A model strategy cannot be created without a valid selected base model."""
  if selected_base_model is None:
    raise SystemsContractError(
      "selected_model_strategy cannot be created without a valid selected_base_model"
    )


def assert_official_approval_state(
  *,
  selected_base_model: str | None,
  selected_adapter: str | None,
  selected_model_strategy: str | None,
  status: str,
  valid_for_official_use: bool,
) -> None:
  """Official approval remains blocked until every required identity is frozen."""
  if valid_for_official_use:
    missing = [
      field
      for field, value in (
        ("selected_base_model", selected_base_model),
        ("selected_adapter", selected_adapter),
        ("selected_model_strategy", selected_model_strategy),
      )
      if value is None
    ]
    if missing:
      raise SystemsContractError(
        f"valid_for_official_use cannot be true while identity fields are null: {missing}"
      )
    if status == "no_selection":
      raise SystemsContractError("valid_for_official_use cannot be true while status is no_selection")
  elif status == "no_selection" and any(
    value is not None
    for value in (selected_base_model, selected_adapter, selected_model_strategy)
  ):
    raise SystemsContractError("status no_selection requires all identity fields to remain null")
