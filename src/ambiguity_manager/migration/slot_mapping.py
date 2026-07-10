"""Deterministic v1-to-v2 legacy slot mapping tables.

Evidence-backed mappings only. See ADR_schema_v2_canonical_record.md.
"""

from __future__ import annotations

from typing import Any

from ambiguity_manager.schema.v2.records import CPC, CPCSlot
from ambiguity_manager.schema.v2.taxonomies import CPCSlotStatus

# VAGUE converter (parse_solution_triplet) and vague_mapping.md prove these keys.
VAGUE_DATASET = "vague"
VAGUE_SLOT_TO_CPC: dict[str, str] = {
  "subject": "actor",
  "action": "action",
  "object": "object",
}

# indirect_requests uses dynamic slot_description keys; no CPC mapping.
INDIRECT_REQUESTS_DATASET = "indirect_requests"


def map_legacy_slots_to_cpc(
  source_dataset: str,
  slots: dict[str, Any],
) -> tuple[CPC, dict[str, Any], list[str]]:
  """Return (cpc, unmapped_slots, unmapped_keys).

  Conservative: only map keys with proven dataset-specific semantics.
  """
  cpc = CPC.empty_unknown()
  unmapped: dict[str, Any] = {}
  unmapped_keys: list[str] = []

  if not slots:
    return cpc, unmapped, unmapped_keys

  if source_dataset == VAGUE_DATASET:
    for key, value in slots.items():
      if key in VAGUE_SLOT_TO_CPC:
        cpc_name = VAGUE_SLOT_TO_CPC[key]
        slot = CPCSlot(
          value=str(value) if value is not None else None,
          status=CPCSlotStatus.FILLED if value not in (None, "") else CPCSlotStatus.MISSING,
        )
        setattr(cpc, cpc_name, slot)
      else:
        unmapped[key] = value
        unmapped_keys.append(key)
    return cpc, unmapped, unmapped_keys

  if source_dataset == INDIRECT_REQUESTS_DATASET:
    for key, value in slots.items():
      unmapped[key] = value
      unmapped_keys.append(key)
    return cpc, unmapped, unmapped_keys

  for key, value in slots.items():
    unmapped[key] = value
    unmapped_keys.append(key)
  return cpc, unmapped, unmapped_keys
