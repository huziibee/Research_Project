"""Tests for canonical schema validation (T01)."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class SchemaValidationTests(unittest.TestCase):
  def setUp(self) -> None:
    from ambiguity_manager.schema import (
      CANONICAL_SCHEMA_VERSION,
      validate_canonical_record,
      validate_manager_input,
    )
    from ambiguity_manager.schema.errors import SchemaValidationError

    self.validate = validate_canonical_record
    self.validate_input = validate_manager_input
    self.SchemaValidationError = SchemaValidationError
    self.version = CANONICAL_SCHEMA_VERSION
    self.minimal = _load_fixture("canonical_record_minimal.json")
    self.compound = _load_fixture("canonical_record_compound_multistep.json")

  def test_valid_minimal_record_accepted(self) -> None:
    self.validate(self.minimal)

  def test_valid_compound_multistep_accepted(self) -> None:
    self.validate(self.compound)

  def test_invalid_route_rejected(self) -> None:
    bad = deepcopy(self.minimal)
    bad["recommended_strategy"] = "always_execute"
    with self.assertRaises(self.SchemaValidationError) as ctx:
      self.validate(bad)
    self.assertIn("recommended_strategy", str(ctx.exception))

  def test_invalid_ambiguity_type_rejected(self) -> None:
    bad = deepcopy(self.minimal)
    bad["ambiguity_types"] = ["referential", "not_a_real_type"]
    with self.assertRaises(self.SchemaValidationError) as ctx:
      self.validate(bad)
    self.assertIn("ambiguity_types", str(ctx.exception))

  def test_missing_required_field_rejected(self) -> None:
    for field in ("id", "command", "source_dataset", "schema_version"):
      bad = deepcopy(self.minimal)
      bad.pop(field)
      with self.assertRaises(self.SchemaValidationError) as ctx:
        self.validate(bad)
      self.assertIn(field, str(ctx.exception))

  def test_multi_label_ambiguity_valid(self) -> None:
    record = deepcopy(self.compound)
    record["ambiguity_types"] = ["referential", "spatial"]
    record["compound_ambiguity_count"] = 2
    self.validate(record)

  def test_compound_count_inconsistent_rejected(self) -> None:
    bad = deepcopy(self.compound)
    bad["compound_ambiguity_count"] = 2
    with self.assertRaises(self.SchemaValidationError) as ctx:
      self.validate(bad)
    self.assertIn("compound_ambiguity_count", str(ctx.exception))

  def test_compound_flag_without_two_types_rejected(self) -> None:
    bad = deepcopy(self.minimal)
    bad["compound_ambiguity"] = True
    bad["compound_ambiguity_count"] = 1
    with self.assertRaises(self.SchemaValidationError) as ctx:
      self.validate(bad)
    self.assertIn("compound_ambiguity", str(ctx.exception))

  def test_primary_not_in_set_rejected(self) -> None:
    bad = deepcopy(self.minimal)
    bad["primary_ambiguity_type"] = "spatial"
    with self.assertRaises(self.SchemaValidationError) as ctx:
      self.validate(bad)
    self.assertIn("primary_ambiguity_type", str(ctx.exception))

  def test_multistep_requires_sequence(self) -> None:
    bad = deepcopy(self.compound)
    bad["strategy_sequence"] = ["clarify"]
    with self.assertRaises(self.SchemaValidationError) as ctx:
      self.validate(bad)
    self.assertIn("strategy_sequence", str(ctx.exception))

  def test_non_multistep_forbids_sequence(self) -> None:
    bad = deepcopy(self.minimal)
    bad["recommended_strategy"] = "clarify"
    bad["strategy_sequence"] = ["clarify", "execute"]
    with self.assertRaises(self.SchemaValidationError) as ctx:
      self.validate(bad)
    self.assertIn("strategy_sequence", str(ctx.exception))

  def test_risk_enum_validation(self) -> None:
    bad = deepcopy(self.minimal)
    bad["risk_level"] = "critical"
    with self.assertRaises(self.SchemaValidationError):
      self.validate(bad)
    ok = deepcopy(self.minimal)
    ok["risk_relevant"] = True
    ok["risk_level"] = "unknown_until_clarified"
    self.validate(ok)

  def test_capability_enum_validation(self) -> None:
    bad = deepcopy(self.minimal)
    bad["capability_status"] = "uncertain"
    with self.assertRaises(self.SchemaValidationError):
      self.validate(bad)
    ok = deepcopy(self.minimal)
    ok["capability_status"] = "partially_capable"
    self.validate(ok)

  def test_provenance_required_fields(self) -> None:
    bad = deepcopy(self.minimal)
    bad.pop("source_dataset")
    with self.assertRaises(self.SchemaValidationError):
      self.validate(bad)

  def test_null_unknown_ambiguity_present(self) -> None:
    record = deepcopy(self.minimal)
    record["ambiguity_present"] = None
    self.validate(record)

  def test_todo_verify_cannot_enable_eligibility(self) -> None:
    bad = deepcopy(self.minimal)
    bad["label_confidence"] = "TODO_VERIFY"
    bad["label_eligibility"]["routing"] = True
    with self.assertRaises(self.SchemaValidationError) as ctx:
      self.validate(bad)
    self.assertIn("label_eligibility", str(ctx.exception))

  def test_adjudicated_gold_invariants(self) -> None:
    bad = deepcopy(self.compound)
    bad["label_confidence"] = "gold_from_source"
    with self.assertRaises(self.SchemaValidationError) as ctx:
      self.validate(bad)
    self.assertIn("record_class", str(ctx.exception))

  def test_source_converted_invariants(self) -> None:
    bad = deepcopy(self.minimal)
    bad["annotation_status"] = "adjudicated"
    with self.assertRaises(self.SchemaValidationError) as ctx:
      self.validate(bad)
    self.assertIn("annotation_status", str(ctx.exception))

  def test_schema_version_mismatch_rejected(self) -> None:
    bad = deepcopy(self.minimal)
    bad["schema_version"] = "9.9.9"
    with self.assertRaises(self.SchemaValidationError) as ctx:
      self.validate(bad)
    self.assertIn("schema_version", str(ctx.exception))

  def test_record_class_prediction_rejected(self) -> None:
    bad = deepcopy(self.minimal)
    bad["record_class"] = "prediction"
    with self.assertRaises(self.SchemaValidationError) as ctx:
      self.validate(bad)
    self.assertIn("record_class", str(ctx.exception))

  def test_manager_input_validation(self) -> None:
    self.validate_input(
      {
        "command": "Bring me the mug.",
        "scene_context": None,
        "dialogue_history": [],
        "capability_context": None,
      }
    )
    with self.assertRaises(self.SchemaValidationError):
      self.validate_input({"command": "", "dialogue_history": []})

  def test_invalid_strategy_sequence_route_rejected(self) -> None:
    bad = deepcopy(self.compound)
    bad["strategy_sequence"] = ["clarify", "maybe_execute"]
    with self.assertRaises(self.SchemaValidationError) as ctx:
      self.validate(bad)
    self.assertIn("strategy_sequence", str(ctx.exception))

  def test_repeated_strategy_sequence_allowed(self) -> None:
    self.validate(self.compound)

  def test_default_split_status_unsplit(self) -> None:
    from ambiguity_manager.schema.records import canonical_record_from_dict

    data = deepcopy(self.minimal)
    data.pop("split_status", None)
    record = canonical_record_from_dict(data)
    self.assertEqual(record.split_status.value, "unsplit")


if __name__ == "__main__":
  unittest.main()
