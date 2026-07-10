"""Canonical schema, taxonomies, and validation for dataset records."""

from ambiguity_manager.schema.errors import SchemaValidationError
from ambiguity_manager.schema.jsonl import read_canonical_jsonl, write_canonical_jsonl
from ambiguity_manager.schema.records import (
  CanonicalRecord,
  CandidateInterpretation,
  LabelEligibility,
  ManagerInput,
  canonical_record_from_dict,
  canonical_record_to_dict,
)
from ambiguity_manager.schema.taxonomies import (
  AmbiguityType,
  AnnotationStatus,
  CapabilityStatus,
  LabelConfidence,
  METRIC_ELIGIBILITY_FIELDS,
  RecordClass,
  RiskLevel,
  RouteLabel,
  SafetyStatus,
  SplitStatus,
)
from ambiguity_manager.schema.validation import validate_canonical_record, validate_manager_input
from ambiguity_manager.schema.version import CANONICAL_SCHEMA_VERSION

__all__ = [
  "CANONICAL_SCHEMA_VERSION",
  "METRIC_ELIGIBILITY_FIELDS",
  "AmbiguityType",
  "AnnotationStatus",
  "CanonicalRecord",
  "CandidateInterpretation",
  "CapabilityStatus",
  "LabelConfidence",
  "LabelEligibility",
  "ManagerInput",
  "RecordClass",
  "RiskLevel",
  "RouteLabel",
  "SafetyStatus",
  "SchemaValidationError",
  "SplitStatus",
  "canonical_record_from_dict",
  "canonical_record_to_dict",
  "read_canonical_jsonl",
  "validate_canonical_record",
  "validate_manager_input",
  "write_canonical_jsonl",
]
