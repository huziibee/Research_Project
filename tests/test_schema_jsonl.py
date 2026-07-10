"""Tests for canonical JSONL I/O (T01)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

FIXTURES = Path(__file__).parent / "fixtures"


class SchemaJsonlTests(unittest.TestCase):
  def setUp(self) -> None:
    from ambiguity_manager.schema.errors import SchemaValidationError
    from ambiguity_manager.schema.jsonl import read_canonical_jsonl, write_canonical_jsonl
    from ambiguity_manager.schema.records import canonical_record_from_dict, canonical_record_to_dict

    self.read_jsonl = read_canonical_jsonl
    self.write_jsonl = write_canonical_jsonl
    self.from_dict = canonical_record_from_dict
    self.to_dict = canonical_record_to_dict
    self.SchemaValidationError = SchemaValidationError
    self.minimal = json.loads((FIXTURES / "canonical_record_minimal.json").read_text(encoding="utf-8"))
    self.compound = json.loads(
      (FIXTURES / "canonical_record_compound_multistep.json").read_text(encoding="utf-8")
    )

    self._tmp = tempfile.TemporaryDirectory()
    self.tmp_path = Path(self._tmp.name)
    (self.tmp_path / "pyproject.toml").write_text("[project]\nname = 'tmp'\n", encoding="utf-8")
    patcher = mock.patch(
      "ambiguity_manager.paths.repo_root",
      return_value=self.tmp_path.resolve(),
    )
    patcher.start()
    self.addCleanup(patcher.stop)
    self.addCleanup(self._tmp.cleanup)

  def test_json_round_trip_lossless(self) -> None:
    record = self.from_dict(self.compound)
    restored = self.from_dict(self.to_dict(record))
    self.assertEqual(self.to_dict(record), self.to_dict(restored))

  def test_duplicate_id_batch_rejected(self) -> None:
    path = self.tmp_path / "dup.jsonl"
    path.write_text(
      json.dumps(self.minimal) + "\n" + json.dumps(self.minimal) + "\n",
      encoding="utf-8",
    )
    with self.assertRaises(self.SchemaValidationError) as ctx:
      self.read_jsonl(path)
    self.assertIn("duplicate", str(ctx.exception).lower())

  def test_jsonl_write_and_read(self) -> None:
    out = self.tmp_path / "data" / "interim" / "sample.jsonl"
    records = [self.from_dict(self.minimal), self.from_dict(self.compound)]
    self.write_jsonl(out, records)
    loaded = self.read_jsonl(out)
    self.assertEqual(len(loaded), 2)
    self.assertEqual(loaded[0].id, "ambik:1")

  def test_jsonl_write_rejects_data_raw(self) -> None:
    from ambiguity_manager.io_guard import RawDataWriteError

    records = [self.from_dict(self.minimal)]
    with self.assertRaises(RawDataWriteError):
      self.write_jsonl(self.tmp_path / "data" / "raw" / "blocked.jsonl", records)


if __name__ == "__main__":
  unittest.main()
