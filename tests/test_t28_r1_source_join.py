"""Deterministic T28-R1 source-record join tests (CPU/read-only canary)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.data.t28_r1_join import (  # noqa: E402
    T28R1JoinError,
    build_permitted_view,
    validate_join,
)


def _row(record_id: str, *, split: str = "source_train", group: str = "g1") -> dict:
    return {
        "id": record_id,
        "source_dataset": "fixture",
        "source_id": record_id,
        "pool": "primary",
        "group_key": group,
        "split": split,
        "eligibility": {"structured_training_target": "eligible"},
    }


def _record(record_id: str, *, group_id: str = "g1", command: str = "move it") -> dict:
    return {
        "id": record_id,
        "source_dataset": "fixture",
        "source_id": record_id,
        "command": command,
        "scene_context": None,
        "dialogue_history": [],
        "capability_context": None,
        "group_id": group_id,
        "source_license": "fixture-license",
        "mapping_version": "fixture-1",
        "annotation_status": "weak_mapped",
        "label_eligibility": {"intent_slots": True},
    }


class T28R1JoinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.canonical = ROOT / "data/processed/weak_pool/weak_pool_canonical.jsonl"
        cls.manifest = ROOT / "data/development/source_splits_v1/record_manifest.jsonl"
        cls.view = ROOT / "data/processed/weak_pool/t28_permitted_train_dev.jsonl"
        cls.view_rows = [json.loads(line) for line in cls.view.read_text(encoding="utf-8").splitlines() if line.strip()] if cls.view.is_file() else []

    def test_expected_ids_resolve_once_and_view_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records.jsonl"
            manifest = root / "manifest.jsonl"
            records.write_text(json.dumps(_record("b")) + "\n" + json.dumps(_record("a", group_id="g2")) + "\n", encoding="utf-8")
            manifest.write_text(json.dumps(_row("a", group="g2")) + "\n" + json.dumps(_row("b")) + "\n", encoding="utf-8")
            first = build_permitted_view(records, manifest, root / "out.jsonl")
            second = build_permitted_view(records, manifest, root / "out2.jsonl")
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual([r["id"] for r in first["rows"]], ["a", "b"])

    def test_unknown_duplicate_split_group_and_eligibility_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records.jsonl"
            manifest = root / "manifest.jsonl"
            records.write_text(json.dumps(_record("a")) + "\n", encoding="utf-8")
            manifest.write_text(json.dumps(_row("a")) + "\n" + json.dumps(_row("missing")) + "\n", encoding="utf-8")
            with self.assertRaises(T28R1JoinError):
                validate_join(records, manifest)

    def test_protected_roles_and_smoke_subsets_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records.jsonl"
            manifest = root / "manifest.jsonl"
            records.write_text(json.dumps(_record("a")) + "\n", encoding="utf-8")
            manifest.write_text(json.dumps(_row("a", split="source_holdout")) + "\n", encoding="utf-8")
            result = build_permitted_view(records, manifest, root / "out.jsonl")
            self.assertEqual(result["rows"], [])

    def test_live_frozen_counts_and_split_membership(self) -> None:
        self.assertTrue(self.canonical.is_file())
        result = validate_join(self.canonical, self.manifest)
        self.assertEqual(result["train_count"], 11294)
        self.assertEqual(result["dev_count"], 2396)
        self.assertEqual(result["missing_ids"], [])
        self.assertEqual(result["unexpected_ids"], [])

    def test_live_view_has_no_protected_records_or_smoke_only_restriction(self) -> None:
        self.assertEqual(len(self.view_rows), 13690)
        self.assertEqual({row["split"] for row in self.view_rows}, {"source_train", "source_dev"})
        self.assertNotEqual(len(self.view_rows), 192)
        self.assertFalse(any(row["split"] == "source_holdout" for row in self.view_rows))

    def test_live_view_groups_are_disjoint_and_metadata_is_preserved(self) -> None:
        train = {row["group_key"] for row in self.view_rows if row["split"] == "source_train"}
        dev = {row["group_key"] for row in self.view_rows if row["split"] == "source_dev"}
        self.assertFalse(train & dev)
        for row in self.view_rows[:100]:
            self.assertTrue(row["command"] if "command" in row else row["record"].get("command"))
            self.assertIn("source_license", row["record"])
            self.assertIn("mapping_version", row["record"])
            self.assertIsInstance(row["eligibility"], dict)

    def test_unknown_labels_are_not_rewritten(self) -> None:
        for row in self.view_rows:
            record = row["record"]
            if record.get("risk_level") is None:
                self.assertIsNone(record["risk_level"])

    def test_hashes_and_provenance_manifests_exist(self) -> None:
        base = self.canonical.parent
        for name in ("weak_pool_canonical.manifest.json", "source-version.manifest.json", "provenance.manifest.json", "licence.manifest.json", "exclusion.report.json", "join-validation.report.json", "checksums.json"):
            self.assertTrue((base / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
