"""Tests for schema v2 canonical enums."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.migration.v1_to_v2 import MigrationAccounting, MigrationError, migrate_v1_dict_to_v2
from ambiguity_manager.schema.errors import SchemaValidationError as V1SchemaValidationError
from ambiguity_manager.schema.v2.errors import SchemaValidationError
from ambiguity_manager.schema.v2.records import LabelEligibility
from ambiguity_manager.schema.v2.taxonomies import CapabilityStatus, RiskLevel
from ambiguity_manager.schema.v2.validation import validate_canonical_record_v2
from ambiguity_manager.schema.v2.version import SCHEMA_VERSION

FIXTURES = Path(__file__).parent / "fixtures" / "migration"


def _base_prediction(**overrides: object) -> dict:
  record = {
    "schema_version": SCHEMA_VERSION,
    "id": "pred:1",
    "record_class": "prediction",
    "source_dataset": "test",
    "source_id": "1",
    "original_split": None,
    "group_id": None,
    "split_status": "unsplit",
    "command": "Synthetic prediction command.",
    "scene_context": None,
    "dialogue_history": [],
    "capability_context": None,
    "speech_act": None,
    "intent_summary": None,
    "cpc": {},
    "candidate_interpretations": [],
    "selected_interpretation": None,
    "unresolved_slots": [],
    "supporting_evidence": [],
    "ambiguity_present": False,
    "ambiguity_types": [],
    "primary_ambiguity_type": None,
    "compound_ambiguity": False,
    "compound_ambiguity_count": 0,
    "risk_relevant": False,
    "risk_level": None,
    "capability_status": None,
    "recommended_strategy": None,
    "strategy_sequence": [],
    "clarification_question": None,
    "clarification_subtype": None,
    "clarification_targets": [],
    "rejection_reason": None,
    "resolved_slots": [],
    "resolution_method": None,
    "resolution_evidence": [],
    "context_sampling_uncertainty": None,
    "migration_version": None,
    "migrated_from_schema_version": None,
    "v1_legacy": None,
    "prediction_metadata": {"model_id": "test-model"},
    "annotation_status": "weak_mapped",
    "label_confidence": "weak_derived",
    "label_eligibility": LabelEligibility().to_dict(),
    "mapping_version": None,
    "source_license": None,
    "mapping_notes": None,
    "source_metadata": None,
  }
  record.update(overrides)
  return record


class SchemaV2EnumTests(unittest.TestCase):
  def test_risk_level_accepts_unknown(self) -> None:
    self.assertEqual(RiskLevel.UNKNOWN.value, "unknown")

  def test_capability_status_accepts_conditional(self) -> None:
    self.assertEqual(CapabilityStatus.CONDITIONAL.value, "conditional")

  def test_legacy_risk_mapping(self) -> None:
    payload = json.loads((FIXTURES / "v1_legacy_enums.json").read_text(encoding="utf-8"))
    accounting = MigrationAccounting()
    record = migrate_v1_dict_to_v2(payload, accounting)
    self.assertEqual(record.risk_level, RiskLevel.UNKNOWN)
    self.assertEqual(accounting.legacy_risk_mappings.get("unknown_until_clarified->unknown"), 1)

  def test_legacy_capability_mapping(self) -> None:
    payload = json.loads((FIXTURES / "v1_legacy_enums.json").read_text(encoding="utf-8"))
    accounting = MigrationAccounting()
    record = migrate_v1_dict_to_v2(payload, accounting)
    self.assertEqual(record.capability_status, CapabilityStatus.CONDITIONAL)
    self.assertEqual(accounting.legacy_capability_mappings.get("partially_capable->conditional"), 1)

  def test_rejects_uncertain_capability(self) -> None:
    payload = json.loads((FIXTURES / "v1_minimal.json").read_text(encoding="utf-8"))
    payload["capability_status"] = "uncertain"
    with self.assertRaises((MigrationError, V1SchemaValidationError)):
      migrate_v1_dict_to_v2(payload)

  def test_v2_parser_rejects_unknown_until_clarified(self) -> None:
    payload = _base_prediction(risk_level="unknown_until_clarified")
    with self.assertRaises(SchemaValidationError):
      validate_canonical_record_v2(payload)

  def test_gold_null_risk_allowed(self) -> None:
    payload = json.loads((FIXTURES / "v1_minimal.json").read_text(encoding="utf-8"))
    record = migrate_v1_dict_to_v2(payload)
    self.assertIsNone(record.risk_level)
    validate_canonical_record_v2(record)

  def test_prediction_null_risk_rejected_when_eligible(self) -> None:
    eligibility = LabelEligibility(risk=True).to_dict()
    payload = _base_prediction(label_eligibility=eligibility)
    with self.assertRaises(SchemaValidationError):
      validate_canonical_record_v2(payload)


if __name__ == "__main__":
  unittest.main()
