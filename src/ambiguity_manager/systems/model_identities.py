"""Model identity contract loader (T16-T24 model identity contract).

This module is the single source of truth for whether a base model, adapter,
or model strategy has been formally selected for official use. Zero-shot
eligibility and adaptation-base eligibility are separate status layers; a
rejected zero-shot result remains immutable even when a checkpoint is later
chosen for QLoRA development. See ``configs/model/selected_identities_v1.json``.
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

STATUS_LAYER_FIELDS: tuple[str, ...] = (
  "zero_shot_candidate_status",
  "adaptation_base_status",
)

ZERO_SHOT_STATUS_VALUES: frozenset[str] = frozenset({"pending", "rejected", "accepted"})
ADAPTATION_BASE_STATUS_VALUES: frozenset[str] = frozenset(
  {"no_viable_adaptation_base", "selected_for_qlora_development"}
)

NULL_SELECTION_STATUSES: frozenset[str] = frozenset(
  {
    "no_selection",
    "no_viable_base_candidate",
    "adaptation_base_pending",
  }
)

CHECKPOINT_IDENTITY_SEPARATOR = "@"


@dataclass(frozen=True)
class SelectedIdentities:
  contract_id: str
  version: str
  zero_shot_candidate_status: str | None
  adaptation_base_status: str | None
  selected_base_model: str | None
  selected_adapter: str | None
  selected_model_strategy: str | None
  status: str
  valid_for_official_use: bool
  bakeoff_outcome: dict[str, Any] | None = None

  def to_dict(self) -> dict[str, Any]:
    payload: dict[str, Any] = {
      "contract_id": self.contract_id,
      "version": self.version,
      "zero_shot_candidate_status": self.zero_shot_candidate_status,
      "adaptation_base_status": self.adaptation_base_status,
      "selected_base_model": self.selected_base_model,
      "selected_adapter": self.selected_adapter,
      "selected_model_strategy": self.selected_model_strategy,
      "status": self.status,
      "valid_for_official_use": self.valid_for_official_use,
    }
    if self.bakeoff_outcome is not None:
      payload["bakeoff_outcome"] = self.bakeoff_outcome
    return payload

  def is_null_selection(self) -> bool:
    return all(getattr(self, field) is None for field in IDENTITY_FIELDS)

  def assert_null_selection(self) -> None:
    """Raise if any identity field is populated.

    T16-T24 and pre-Phase-D adaptation work must never select a model,
    adapter, or strategy. ``no_viable_base_candidate`` and
    ``adaptation_base_pending`` are allowed null-selection statuses after a
    failed zero-shot bake-off or before adaptation-base selection.
    """
    populated = [field for field in IDENTITY_FIELDS if getattr(self, field) is not None]
    if populated:
      raise SystemsContractError(
        f"model identity contract expected null selection but found populated fields: {populated}"
      )
    if self.status not in NULL_SELECTION_STATUSES:
      raise SystemsContractError(
        "model identity contract status must be one of "
        f"{sorted(NULL_SELECTION_STATUSES)!r}, found {self.status!r}"
      )
    if self.valid_for_official_use:
      raise SystemsContractError(
        "model identity contract must not be valid_for_official_use while selection is null"
      )


def _default_path() -> Path:
  return ProjectPaths.from_repo_root().configs / "model" / "selected_identities_v1.json"


def _infer_zero_shot_status(raw: dict[str, Any]) -> str | None:
  explicit = raw.get("zero_shot_candidate_status")
  if explicit is not None:
    return str(explicit)
  bakeoff = raw.get("bakeoff_outcome")
  if isinstance(bakeoff, dict):
    nested = bakeoff.get("zero_shot_candidate_status")
    if nested is not None:
      return str(nested)
    decision = str(bakeoff.get("decision", ""))
    if decision in {"no_viable_base_candidate", "no_viable_zero_shot_candidate"}:
      return "rejected"
  status = str(raw.get("status", ""))
  if status == "no_viable_base_candidate":
    return "rejected"
  return None


def _validate_status_layers(raw: dict[str, Any]) -> list[str]:
  errors: list[str] = []
  zero_shot = raw.get("zero_shot_candidate_status", _infer_zero_shot_status(raw))
  if zero_shot is not None and zero_shot not in ZERO_SHOT_STATUS_VALUES:
    errors.append(f"zero_shot_candidate_status must be one of {sorted(ZERO_SHOT_STATUS_VALUES)}")
  adaptation = raw.get("adaptation_base_status")
  if adaptation is not None and adaptation not in ADAPTATION_BASE_STATUS_VALUES:
    errors.append(
      f"adaptation_base_status must be null or one of {sorted(ADAPTATION_BASE_STATUS_VALUES)}"
    )
  if adaptation == "selected_for_qlora_development" and raw.get("selected_base_model") is None:
    errors.append("adaptation_base_status selected_for_qlora_development requires selected_base_model")
  if raw.get("selected_base_model") is None and adaptation is not None:
    errors.append("adaptation_base_status must remain null while selected_base_model is null")
  return errors


def load_selected_identities(path: Path | None = None) -> SelectedIdentities:
  """Load and structurally validate the model identity contract."""
  resolved = path or _default_path()
  raw = json.loads(resolved.read_text(encoding="utf-8"))
  if not isinstance(raw, dict):
    raise SystemsContractError("selected_identities contract must be an object")
  missing = [key for key in ("contract_id", "version", "status") if key not in raw]
  if missing:
    raise SystemsContractError(f"selected_identities contract missing fields: {missing}")
  layer_errors = _validate_status_layers(raw)
  if layer_errors:
    raise SystemsContractError("selected_identities contract invalid:\n- " + "\n- ".join(layer_errors))
  for field in IDENTITY_FIELDS:
    value = raw.get(field)
    if value is not None and not isinstance(value, str):
      raise SystemsContractError(f"{field} must be a string or null")
  bakeoff = raw.get("bakeoff_outcome")
  if bakeoff is not None and not isinstance(bakeoff, dict):
    raise SystemsContractError("bakeoff_outcome must be an object when present")
  return SelectedIdentities(
    contract_id=str(raw["contract_id"]),
    version=str(raw["version"]),
    zero_shot_candidate_status=_infer_zero_shot_status(raw),
    adaptation_base_status=raw.get("adaptation_base_status"),
    selected_base_model=raw.get("selected_base_model"),
    selected_adapter=raw.get("selected_adapter"),
    selected_model_strategy=raw.get("selected_model_strategy"),
    status=str(raw.get("status", "unknown")),
    valid_for_official_use=bool(raw.get("valid_for_official_use", False)),
    bakeoff_outcome=dict(bakeoff) if isinstance(bakeoff, dict) else None,
  )


def assert_null_selection(path: Path | None = None) -> SelectedIdentities:
  """Load the contract and assert every identity field is currently null."""
  identities = load_selected_identities(path)
  identities.assert_null_selection()
  return identities


def assert_zero_shot_status_immutable(
  *,
  recorded_status: str,
  proposed_status: str,
) -> None:
  """A rejected zero-shot outcome must not be rewritten as accepted or pending."""
  if recorded_status == "rejected" and proposed_status != "rejected":
    raise SystemsContractError(
      "zero_shot_candidate_status is immutable once rejected "
      f"(recorded {recorded_status!r}, proposed {proposed_status!r})"
    )


def assert_adaptation_base_selection_scope(
  *,
  selected_base_model: str | None,
  selected_adapter: str | None,
  selected_model_strategy: str | None,
  adaptation_base_status: str | None,
  valid_for_official_use: bool,
) -> None:
  """Selecting an adaptation base must not imply adapter, strategy, or official approval."""
  if adaptation_base_status == "selected_for_qlora_development":
    if selected_base_model is None:
      raise SystemsContractError(
        "adaptation_base_status selected_for_qlora_development requires selected_base_model"
      )
    if selected_adapter is not None:
      raise SystemsContractError(
        "adaptation-base selection must not populate selected_adapter"
      )
    if selected_model_strategy is not None:
      raise SystemsContractError(
        "adaptation-base selection must not populate selected_model_strategy"
      )
    if valid_for_official_use:
      raise SystemsContractError(
        "adaptation-base selection is development-only; valid_for_official_use must remain false"
      )


def assert_strategy_cannot_replace_base(
  *,
  original_selected_base_model: str,
  proposed_selected_base_model: str | None,
  selected_model_strategy: str | None,
) -> None:
  """Registering a model strategy must not silently replace the selected base."""
  if selected_model_strategy is None:
    return
  if proposed_selected_base_model != original_selected_base_model:
    raise SystemsContractError(
      "selected_model_strategy registration cannot replace selected_base_model "
      f"(expected {original_selected_base_model!r}, got {proposed_selected_base_model!r})"
    )


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


def assert_direct_base_uses_no_adapter(
  *,
  selected_base_model: str | None,
  selected_adapter: str | None,
  forbids_selected_adapter: bool,
) -> None:
  """Direct-base baseline systems must run against the unadapted checkpoint."""
  if not forbids_selected_adapter:
    return
  if selected_base_model is not None and selected_adapter is not None:
    raise SystemsContractError(
      "direct-base baseline requires selected_adapter to remain null"
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
