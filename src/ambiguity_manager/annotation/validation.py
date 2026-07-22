"""Validation for candidates and annotator responses."""

from __future__ import annotations

from typing import Any

from ambiguity_manager.annotation.roles import RolePolicyError, assert_official_annotator_role
from ambiguity_manager.annotation.schema import (
  ANNOTATION_SCHEMA_VERSION,
  GOLD_FIELD_MARKERS,
  HANDBOOK_VERSION,
  PACKAGE_VERSION,
  load_annotation_schema,
  load_intent_taxonomy,
)
from ambiguity_manager.schema.v2.taxonomies import (
  AmbiguityType,
  CapabilityStatus,
  CPC_SLOT_NAMES,
  CPCSlotStatus,
  RiskLevel,
  RouteLabel,
)


class AnnotationValidationError(ValueError):
  pass


def _contains_gold_fields(payload: dict[str, Any], prefix: str = "") -> list[str]:
  hits: list[str] = []
  for key, value in payload.items():
    path = f"{prefix}.{key}" if prefix else key
    lowered = key.lower()
    if any(marker in lowered for marker in GOLD_FIELD_MARKERS) or lowered.startswith("gold_"):
      hits.append(path)
    if isinstance(value, dict):
      hits.extend(_contains_gold_fields(value, path))
  return hits


def validate_no_gold_fields(payload: dict[str, Any]) -> list[str]:
  schema = load_annotation_schema()
  prohibited = set(schema.get("prohibited_gold_fields", []))
  errors: list[str] = []
  for key in payload:
    if key in prohibited or key.startswith("gold_"):
      errors.append(f"prohibited gold field present: {key}")
  errors.extend(f"prohibited gold-like field: {p}" for p in _contains_gold_fields(payload))
  return sorted(set(errors))


def validate_cpc(cpc: Any) -> list[str]:
  errors: list[str] = []
  if not isinstance(cpc, dict):
    return ["cpc must be an object"]
  for slot in CPC_SLOT_NAMES:
    if slot not in cpc:
      errors.append(f"cpc missing slot {slot}")
      continue
    raw = cpc[slot]
    if not isinstance(raw, dict):
      errors.append(f"cpc.{slot} must be an object")
      continue
    status = raw.get("status")
    value = raw.get("value")
    try:
      CPCSlotStatus(status)
    except ValueError:
      errors.append(f"invalid CPC status for {slot}: {status!r}")
    if value is not None and not isinstance(value, str):
      errors.append(f"cpc.{slot}.value must be string or null")
    if status == CPCSlotStatus.FILLED.value and not value:
      errors.append(f"cpc.{slot} status filled requires non-empty value")
  return errors


def validate_candidate_record(record: dict[str, Any], *, require_hidden: bool = True) -> list[str]:
  schema = load_annotation_schema()
  errors = validate_no_gold_fields(record)
  required = schema["immutable_visible_fields"]["required"]
  for field in required:
    if field not in record:
      errors.append(f"missing required candidate field: {field}")
  if record.get("handbook_version") != HANDBOOK_VERSION:
    errors.append("handbook_version mismatch")
  if record.get("annotation_schema_version") != ANNOTATION_SCHEMA_VERSION:
    errors.append("annotation_schema_version mismatch")
  if record.get("package_version") != PACKAGE_VERSION:
    errors.append("package_version mismatch")
  allowed_prov = set(schema["immutable_visible_fields"]["visible_provenance_category_allowed"])
  if record.get("visible_provenance_category") not in allowed_prov:
    errors.append("invalid visible_provenance_category")
  allowed_part = set(schema["immutable_visible_fields"]["dataset_partition_allowed"])
  if record.get("dataset_partition") not in allowed_part:
    errors.append("invalid dataset_partition")
  if not isinstance(record.get("command"), str) or not record.get("command", "").strip():
    errors.append("command must be a non-empty string")
  if not isinstance(record.get("dialogue_history"), list):
    errors.append("dialogue_history must be a list")
  if require_hidden:
    hidden = record.get("hidden")
    if not isinstance(hidden, dict):
      errors.append("candidate source records require hidden author/admin metadata object")
    else:
      for key in ("design_cell", "seed_id", "group_id"):
        if key not in hidden:
          errors.append(f"hidden metadata missing {key}")
  return errors


def validate_annotator_package_record(record: dict[str, Any]) -> list[str]:
  """Visible package records must not expose hidden author fields."""
  errors = validate_candidate_record(record, require_hidden=False)
  if "hidden" in record:
    errors.append("annotator package must not include hidden metadata")
  for key in load_annotation_schema()["hidden_author_admin_fields"]:
    if key in record:
      errors.append(f"hidden field leaked into annotator package: {key}")
  return errors


def validate_annotator_response(response: dict[str, Any]) -> list[str]:
  schema = load_annotation_schema()
  intent = load_intent_taxonomy()
  errors = validate_no_gold_fields(response)
  for field in schema["annotator_response_fields"]["required"]:
    if field not in response:
      errors.append(f"missing required annotator field: {field}")
  speech = response.get("speech_act")
  if speech not in set(intent["labels"]):
    errors.append(f"invalid speech_act: {speech!r}")
  errors.extend(validate_cpc(response.get("cpc")))
  try:
    assert_official_annotator_role(str(response.get("annotator_role")))
  except RolePolicyError as exc:
    errors.append(str(exc))
  amb = response.get("ambiguity_types")
  if not isinstance(amb, list):
    errors.append("ambiguity_types must be a list")
  else:
    for item in amb:
      try:
        AmbiguityType(item)
      except ValueError:
        errors.append(f"invalid ambiguity type: {item!r}")
  try:
    RiskLevel(response.get("risk_level"))
  except ValueError:
    errors.append(f"invalid risk_level: {response.get('risk_level')!r}")
  try:
    CapabilityStatus(response.get("capability_status"))
  except ValueError:
    errors.append(f"invalid capability_status: {response.get('capability_status')!r}")
  strategy = response.get("recommended_strategy")
  try:
    RouteLabel(strategy)
  except ValueError:
    errors.append(f"invalid recommended_strategy: {strategy!r}")
  count = response.get("compound_ambiguity_count")
  if not isinstance(count, int) or count < 0:
    errors.append("compound_ambiguity_count must be a non-negative int")
  elif isinstance(amb, list) and count != len(set(amb)):
    errors.append("compound_ambiguity_count must equal distinct ambiguity_types")
  if strategy == RouteLabel.MULTI_STEP.value:
    seq = response.get("strategy_sequence")
    if not isinstance(seq, list) or len(seq) < 2:
      errors.append("multi_step requires strategy_sequence with >= 2 steps")
  if strategy == RouteLabel.CLARIFY.value:
    if not response.get("clarification_targets"):
      errors.append("clarify requires clarification_targets")
    if not response.get("clarification_question"):
      errors.append("clarify requires clarification_question")
  if strategy == RouteLabel.FACE_PRESERVING_REJECTION.value:
    if not response.get("rejection_reason"):
      errors.append("face_preserving_rejection requires rejection_reason")
  if strategy == RouteLabel.SILENTLY_RESOLVE.value:
    if not response.get("resolved_slots"):
      errors.append("silently_resolve requires resolved_slots")
  if response.get("confidence") not in set(schema["confidence_allowed"]):
    errors.append("invalid confidence")
  if response.get("handbook_version") != HANDBOOK_VERSION:
    errors.append("response handbook_version mismatch")
  if response.get("annotation_schema_version") != ANNOTATION_SCHEMA_VERSION:
    errors.append("response annotation_schema_version mismatch")
  if response.get("package_version") != PACKAGE_VERSION:
    errors.append("response package_version mismatch")
  if not isinstance(response.get("candidate_interpretations"), list):
    errors.append("candidate_interpretations must be a list")
  return errors


def empty_cpc(status: str = "not_applicable") -> dict[str, dict[str, Any]]:
  return {name: {"value": None, "status": status} for name in CPC_SLOT_NAMES}
