"""Tests for schema v2 CPC, interpretations, routing, and invariants."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.migration.v1_to_v2 import migrate_v1_dict_to_v2
from ambiguity_manager.schema.v2.errors import SchemaValidationError
from ambiguity_manager.schema.v2.records import (
  CandidateInterpretationFrame,
  CPC,
  CPCSlot,
  EvidenceRef,
  LabelEligibility,
  PredictionMetadata,
  SelectedInterpretation,
  canonical_record_v2_from_dict,
)
from ambiguity_manager.schema.v2.taxonomies import CPCSlotStatus, RouteLabel
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


class SchemaV2ValidationTests(unittest.TestCase):
  def test_malformed_cpc_rejected(self) -> None:
    payload = _base_prediction(cpc={"action": {"value": 123, "status": "filled"}})
    with self.assertRaises(SchemaValidationError):
      validate_canonical_record_v2(payload)

  def test_cpc_slot_status_validation(self) -> None:
    slot = CPCSlot(value="move", status=CPCSlotStatus.FILLED)
    self.assertEqual(slot.to_dict()["status"], "filled")

  def test_vague_slot_mapping(self) -> None:
    payload = json.loads((FIXTURES / "v1_vague_slots.json").read_text(encoding="utf-8"))
    record = migrate_v1_dict_to_v2(payload)
    self.assertEqual(record.cpc.actor.value, "person")
    self.assertEqual(record.cpc.action.value, "pick")
    self.assertEqual(record.cpc.object.value, "cup")
    self.assertIsNone(record.selected_interpretation)
    self.assertEqual(record.v1_legacy.resolved_interpretation, None)

  def test_indirect_slots_preserved_in_legacy(self) -> None:
    payload = json.loads((FIXTURES / "v1_indirect_slots.json").read_text(encoding="utf-8"))
    record = migrate_v1_dict_to_v2(payload)
    self.assertEqual(record.v1_legacy.slots, {"destination_city": "Paris"})
    self.assertEqual(record.cpc.actor.status, CPCSlotStatus.UNKNOWN)

  def test_candidate_interpretation_migration(self) -> None:
    payload = json.loads((FIXTURES / "v1_legacy_enums.json").read_text(encoding="utf-8"))
    record = migrate_v1_dict_to_v2(payload)
    self.assertEqual(len(record.candidate_interpretations), 1)
    self.assertEqual(record.candidate_interpretations[0].frame_id, "test:legacy-enums:candidate:0")
    self.assertEqual(record.candidate_interpretations[0].text, "Candidate A")

  def test_selected_interpretation_requires_evidence(self) -> None:
    payload = _base_prediction(
      candidate_interpretations=[
        {"frame_id": "pred:1:candidate:0", "text": "A", "cpc": {}},
      ],
      selected_interpretation={"frame_id": "pred:1:candidate:0", "supporting_evidence": []},
    )
    with self.assertRaises(SchemaValidationError):
      validate_canonical_record_v2(payload)

  def test_unresolved_slots_migrated(self) -> None:
    payload = json.loads((FIXTURES / "v1_legacy_enums.json").read_text(encoding="utf-8"))
    record = migrate_v1_dict_to_v2(payload)
    self.assertEqual([item.slot_name for item in record.unresolved_slots], ["slot_x"])
    self.assertEqual(record.v1_legacy.missing_slots, ["slot_x"])

  def test_resolved_interpretation_not_selected(self) -> None:
    payload = json.loads((FIXTURES / "v1_legacy_enums.json").read_text(encoding="utf-8"))
    record = migrate_v1_dict_to_v2(payload)
    self.assertIsNone(record.selected_interpretation)
    self.assertEqual(record.v1_legacy.resolved_interpretation, "Resolved text")

  def test_multi_step_invariant(self) -> None:
    payload = _base_prediction(
      recommended_strategy="multi_step",
      strategy_sequence=["clarify"],
    )
    with self.assertRaises(SchemaValidationError):
      validate_canonical_record_v2(payload)

  def test_silent_resolve_prediction_requires_resolution(self) -> None:
    payload = _base_prediction(recommended_strategy="silently_resolve")
    with self.assertRaises(SchemaValidationError):
      validate_canonical_record_v2(payload)

  def test_clarify_prediction_requires_targets_and_question(self) -> None:
    payload = _base_prediction(recommended_strategy="clarify")
    with self.assertRaises(SchemaValidationError):
      validate_canonical_record_v2(payload)

  def test_rejection_prediction_requires_reason(self) -> None:
    payload = _base_prediction(recommended_strategy="face_preserving_rejection")
    with self.assertRaises(SchemaValidationError):
      validate_canonical_record_v2(payload)

  def test_gold_silent_resolve_without_resolution_allowed(self) -> None:
    payload = json.loads((FIXTURES / "v1_minimal.json").read_text(encoding="utf-8"))
    payload["recommended_strategy"] = "silently_resolve"
    record = migrate_v1_dict_to_v2(payload)
    validate_canonical_record_v2(record)


if __name__ == "__main__":
  unittest.main()
