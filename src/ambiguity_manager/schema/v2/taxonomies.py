"""Frozen taxonomy enums for canonical schema v2 records."""

from __future__ import annotations

from enum import StrEnum


class RouteLabel(StrEnum):
  EXECUTE = "execute"
  CLARIFY = "clarify"
  SILENTLY_RESOLVE = "silently_resolve"
  FACE_PRESERVING_REJECTION = "face_preserving_rejection"
  MULTI_STEP = "multi_step"


class AmbiguityType(StrEnum):
  REFERENTIAL = "referential"
  SPATIAL = "spatial"
  PRAGMATIC = "pragmatic"
  TEMPORAL = "temporal"
  QUANTITATIVE = "quantitative"
  PREFERENCE = "preference"
  COMMONSENSE = "commonsense"
  SAFETY_PRECONDITION = "safety_precondition"
  CAPABILITY = "capability"
  CONTEXTUAL = "contextual"


class RiskLevel(StrEnum):
  NONE = "none"
  LOW = "low"
  MEDIUM = "medium"
  HIGH = "high"
  UNKNOWN = "unknown"


class CapabilityStatus(StrEnum):
  CAPABLE = "capable"
  CONDITIONAL = "conditional"
  INCAPABLE = "incapable"
  UNKNOWN = "unknown"


class LabelConfidence(StrEnum):
  GOLD_FROM_SOURCE = "gold_from_source"
  WEAK_DERIVED = "weak_derived"
  MANUAL_GOLD = "manual_gold"
  TODO_VERIFY = "TODO_VERIFY"


class AnnotationStatus(StrEnum):
  SOURCE_NATIVE = "source_native"
  WEAK_MAPPED = "weak_mapped"
  MANUALLY_ANNOTATED = "manually_annotated"
  ADJUDICATED = "adjudicated"


class RecordClass(StrEnum):
  SOURCE_CONVERTED = "source_converted"
  ADJUDICATED_GOLD = "adjudicated_gold"
  PREDICTION = "prediction"


class SplitStatus(StrEnum):
  UNSPLIT = "unsplit"
  TRAIN = "train"
  DEV = "dev"
  TEST = "test"
  GOLD_MANUAL = "gold_manual"
  CHALLENGE = "challenge"
  EXCLUDED = "excluded"


class SafetyStatus(StrEnum):
  SAFE = "safe"
  UNSAFE = "unsafe"
  UNKNOWN = "unknown"


class CPCSlotStatus(StrEnum):
  FILLED = "filled"
  MISSING = "missing"
  UNKNOWN = "unknown"
  NOT_APPLICABLE = "not_applicable"


CPC_SLOT_NAMES: tuple[str, ...] = (
  "action",
  "actor",
  "object",
  "object_attributes",
  "destination",
  "spatial_relation",
  "quantity",
  "time",
  "recipient",
  "tool",
  "conditions",
  "constraints",
  "negation",
)

METRIC_ELIGIBILITY_FIELDS: tuple[str, ...] = (
  "routing",
  "ambiguity",
  "risk",
  "capability",
  "clarification_decision",
  "clarification_target",
  "intent_slots",
  "rejection",
  "compound_sequence",
  "context_benefit",
)

V1_LEGACY_RISK_VALUES: frozenset[str] = frozenset({"unknown_until_clarified"})
V1_LEGACY_CAPABILITY_VALUES: frozenset[str] = frozenset({"partially_capable"})
REJECTED_LEGACY_VALUES: frozenset[str] = frozenset({"uncertain"})
