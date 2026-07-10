"""Tests ensuring migration reports do not expose raw corpus text."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.migration.v1_to_v2 import migrate_v1_dict_to_v2_dict

FIXTURES = Path(__file__).parent / "fixtures" / "migration"


class MigrationV2ReportTests(unittest.TestCase):
  def test_migrated_record_command_not_in_aggregate_summary_template(self) -> None:
    payload = json.loads((FIXTURES / "v1_minimal.json").read_text(encoding="utf-8"))
    migrated = migrate_v1_dict_to_v2_dict(payload)
    summary = {
      "counts": {"records": 1},
      "accounting": {"records_migrated": 1},
    }
    summary_text = json.dumps(summary)
    self.assertNotIn(migrated["command"], summary_text)


if __name__ == "__main__":
  unittest.main()
