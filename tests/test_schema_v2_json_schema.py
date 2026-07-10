"""Tests for deterministic JSON Schema export consistency with schema v2 Python definitions."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.data_audit.readers import streaming_sha256
from ambiguity_manager.schema.v2.json_schema import (
  SCHEMA_JSON_FILENAME,
  build_canonical_record_v2_json_schema,
  canonical_record_v2_json_schema_text,
  schema_json_path,
  write_schema_json,
)
from ambiguity_manager.schema.v2.taxonomies import (
  AmbiguityType,
  AnnotationStatus,
  CapabilityStatus,
  CPC_SLOT_NAMES,
  CPCSlotStatus,
  LabelConfidence,
  METRIC_ELIGIBILITY_FIELDS,
  RecordClass,
  RiskLevel,
  RouteLabel,
  SafetyStatus,
  SplitStatus,
)
from ambiguity_manager.schema.v2.version import SCHEMA_VERSION

SCHEMA_PATH = schema_json_path()


class SchemaV2JsonSchemaTests(unittest.TestCase):
  def test_schema_json_file_exists(self) -> None:
    self.assertTrue(SCHEMA_PATH.is_file(), f"missing committed {SCHEMA_JSON_FILENAME}")

  def test_deterministic_schema_bytes(self) -> None:
    generated = canonical_record_v2_json_schema_text()
    on_disk = SCHEMA_PATH.read_text(encoding="utf-8")
    self.assertEqual(generated, on_disk)
    self.assertEqual(
      streaming_sha256(SCHEMA_PATH),
      streaming_sha256(Path(write_schema_json(SCHEMA_PATH.parent / ".regen_schema.json"))),
    )
    (SCHEMA_PATH.parent / ".regen_schema.json").unlink(missing_ok=True)

  def test_schema_version_const(self) -> None:
    schema = build_canonical_record_v2_json_schema()
    self.assertEqual(schema["schema_version"], SCHEMA_VERSION)
    self.assertEqual(schema["schema_version"], "2.0.0")

  def test_enum_consistency_risk_level(self) -> None:
    schema = build_canonical_record_v2_json_schema()
    risk_enum = set(schema["definitions"]["risk_level"]["enum"])
    self.assertEqual(risk_enum, {member.value for member in RiskLevel})

  def test_enum_consistency_capability_status(self) -> None:
    schema = build_canonical_record_v2_json_schema()
    cap_enum = set(schema["definitions"]["capability_status"]["enum"])
    self.assertEqual(cap_enum, {member.value for member in CapabilityStatus})

  def test_enum_consistency_record_class(self) -> None:
    schema = build_canonical_record_v2_json_schema()
    classes = set(schema["definitions"]["record_class"]["enum"])
    self.assertEqual(classes, {member.value for member in RecordClass})

  def test_cpc_slot_names_present(self) -> None:
    schema = build_canonical_record_v2_json_schema()
    gold_props = schema["oneOf"][0]["properties"]
    cpc_props = set(gold_props["cpc"]["properties"].keys())
    self.assertEqual(cpc_props, set(CPC_SLOT_NAMES))

  def test_cpc_slot_status_enum(self) -> None:
    schema = build_canonical_record_v2_json_schema()
    gold_props = schema["oneOf"][0]["properties"]
    status_enum = set(gold_props["cpc"]["properties"]["action"]["properties"]["status"]["enum"])
    self.assertEqual(status_enum, {member.value for member in CPCSlotStatus})

  def test_label_eligibility_fields(self) -> None:
    schema = build_canonical_record_v2_json_schema()
    gold_props = schema["oneOf"][0]["properties"]
    eligibility_props = set(gold_props["label_eligibility"]["properties"].keys())
    self.assertEqual(eligibility_props, set(METRIC_ELIGIBILITY_FIELDS))

  def test_gold_vs_prediction_distinction(self) -> None:
    schema = build_canonical_record_v2_json_schema()
    gold = schema["oneOf"][0]
    prediction = schema["oneOf"][1]
    self.assertIn(RecordClass.PREDICTION.value, prediction["properties"]["record_class"]["const"])
    self.assertIn("prediction_metadata", prediction["required"])
    self.assertEqual(gold["properties"]["prediction_metadata"], {"type": "null"})

  def test_required_top_level_fields(self) -> None:
    schema = build_canonical_record_v2_json_schema()
    required = set(schema["oneOf"][0]["required"])
    for field in (
      "schema_version",
      "id",
      "record_class",
      "source_dataset",
      "command",
      "annotation_status",
      "label_confidence",
      "label_eligibility",
      "cpc",
    ):
      self.assertIn(field, required)

  def test_no_corpus_content_in_schema(self) -> None:
    text = SCHEMA_PATH.read_text(encoding="utf-8").lower()
    for forbidden in ("fill the food", "synthetic", "utterance", "paris"):
      self.assertNotIn(forbidden, text)

  def test_all_taxonomy_enums_referenced(self) -> None:
    schema = build_canonical_record_v2_json_schema()
    defs = schema["definitions"]
    self.assertEqual(set(defs["ambiguity_type"]["enum"]), {m.value for m in AmbiguityType})
    self.assertEqual(set(defs["route_label"]["enum"]), {m.value for m in RouteLabel})
    gold = schema["oneOf"][0]["properties"]
    self.assertEqual(
      set(gold["annotation_status"]["enum"]),
      {m.value for m in AnnotationStatus},
    )
    self.assertEqual(
      set(gold["label_confidence"]["enum"]),
      {m.value for m in LabelConfidence},
    )
    self.assertEqual(
      set(gold["split_status"]["enum"]),
      {m.value for m in SplitStatus},
    )
    candidate = gold["candidate_interpretations"]["items"]["properties"]["safety_status"]
    safety_enum = set(candidate["oneOf"][1]["enum"])
    self.assertEqual(safety_enum, {m.value for m in SafetyStatus})


if __name__ == "__main__":
  unittest.main()
