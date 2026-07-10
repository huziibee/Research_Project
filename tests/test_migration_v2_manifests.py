"""Tests for deterministic schema v2 migration manifests."""

from __future__ import annotations

import json
import unittest

from ambiguity_manager.migration.run_migration import _deterministic_json
from ambiguity_manager.paths import repo_relative_path


class MigrationV2ManifestTests(unittest.TestCase):
  def test_deterministic_json_bytes(self) -> None:
    payload = {"b": 2, "a": 1, "nested": {"z": 9, "y": 8}}
    first = _deterministic_json(payload)
    second = _deterministic_json(payload)
    self.assertEqual(first, second)
    self.assertEqual(first, '{"a":1,"b":2,"nested":{"y":8,"z":9}}')

  def test_repo_relative_paths_use_forward_slashes(self) -> None:
    # repo_relative_path tested indirectly via migration outputs in integration.
    self.assertIn("/", repo_relative_path("data/interim/ambik/ambik_canonical.jsonl"))


if __name__ == "__main__":
  unittest.main()
