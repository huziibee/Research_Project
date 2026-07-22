"""Model-independent ambiguity-manager system contracts and adapters."""

from __future__ import annotations

from ambiguity_manager.systems.contracts import (
  StructuredAnalysis,
  SystemInput,
  SystemResult,
)
from ambiguity_manager.systems.errors import (
  ProviderUnavailableError,
  SystemsContractError,
)
from ambiguity_manager.systems.variants import (
  SYSTEM_IDS,
  get_system,
  list_systems,
)

__all__ = [
  "SYSTEM_IDS",
  "ProviderUnavailableError",
  "StructuredAnalysis",
  "SystemInput",
  "SystemResult",
  "SystemsContractError",
  "get_system",
  "list_systems",
]
