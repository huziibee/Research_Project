"""Tests for deterministic v1-to-v2 migration."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.migration.v1_to_v2 import (
  MigrationAccounting,
  migrate_v1_dict_to_v2,
  migrate_v1_dict_to_v2_dict,
)
from ambiguity_manager.schema.v2.version import SCHEMA_VERSION

FIXTURES = Path(__file__).parent / "fixtures" / "migration"


class MigrationV1ToV2Tests(unittest.TestCase):
  def test_deterministic_migration_bytes(self) -> None:
    payload = json.loads((FIXTURES / "v1_minimal.json").read_text(encoding="utf-8"))
    first = json.dumps(migrate_v1_dict_to_v2_dict(payload), sort_keys=True)
    second = json.dumps(migrate_v1_dict_to_v2_dict(payload), sort_keys=True)
    self.assertEqual(first, second)

  def test_id_preservation(self) -> None:
    payload = json.loads((FIXTURES / "v1_minimal.json").read_text(encoding="utf-8"))
    record = migrate_v1_dict_to_v2(payload)
    self.assertEqual(record.id, "test:minimal")
    self.assertEqual(record.schema_version, SCHEMA_VERSION)
    self.assertEqual(record.migrated_from_schema_version, "1.0.0")

  def test_source_reordering_stability(self) -> None:
    a = json.loads((FIXTURES / "v1_minimal.json").read_text(encoding="utf-8"))
    b = json.loads((FIXTURES / "v1_vague_slots.json").read_text(encoding="utf-8"))
    ids_a_first = [
      migrate_v1_dict_to_v2(item).id for item in (a, b)
    ]
    ids_b_first = [
      migrate_v1_dict_to_v2(item).id for item in (b, a)
    ]
    self.assertEqual(sorted(ids_a_first), sorted(ids_b_first))

  def test_clarification_question_rename(self) -> None:
    payload = json.loads((FIXTURES / "v1_legacy_enums.json").read_text(encoding="utf-8"))
    record = migrate_v1_dict_to_v2(payload)
    self.assertEqual(record.clarification_question, "Which slot?")
    self.assertEqual(record.v1_legacy.gold_clarification_question, "Which slot?")

  def test_unmappable_accounting(self) -> None:
    accounting = MigrationAccounting()
    payload = json.loads((FIXTURES / "v1_minimal.json").read_text(encoding="utf-8"))
    migrate_v1_dict_to_v2(payload, accounting)
    self.assertGreater(accounting.unmappable_fields.get("not_present_in_v1:speech_act", 0), 0)


if __name__ == "__main__":
  unittest.main()
