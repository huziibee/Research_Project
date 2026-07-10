"""Canonical schema version 2."""

from ambiguity_manager.schema.v2.errors import SchemaValidationError
from ambiguity_manager.schema.v2.records import (
  CanonicalRecordV2,
  canonical_record_v2_from_dict,
  canonical_record_v2_to_dict,
)
from ambiguity_manager.schema.v2.taxonomies import (
  CapabilityStatus,
  CPCSlotStatus,
  RiskLevel,
)
from ambiguity_manager.schema.v2.validation import validate_canonical_record_v2
from ambiguity_manager.schema.v2.version import SCHEMA_VERSION

__all__ = [
  "SCHEMA_VERSION",
  "SchemaValidationError",
  "CanonicalRecordV2",
  "RiskLevel",
  "CapabilityStatus",
  "CPCSlotStatus",
  "canonical_record_v2_from_dict",
  "canonical_record_v2_to_dict",
  "validate_canonical_record_v2",
]
