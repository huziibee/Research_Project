"""T27C data isolation / leakage tests (CPU-only)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.data.model_selection_set import (  # noqa: E402
    CALIBRATION_ID_RE,
    FUTURE_MANUAL_ID_RES,
)
from ambiguity_manager.model.t27c_datasets import (  # noqa: E402
    HISTORICAL_FORBIDDEN_IDS,
    JOB6059_VAL_IDS,
    T27B_DIAGNOSTIC_IDS,
    T27B_SEALED_IDS,
)


def _ids(path: Path) -> set[str]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return {str(x) for x in manifest["record_ids"]}


def _groups(records_path: Path) -> set[str]:
    groups: set[str] = set()
    for line in records_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            groups.add(str(json.loads(line)["group_key"]))
    return groups


class T27CDataIsolationTests(unittest.TestCase):
    def test_counts_and_flags(self) -> None:
        train = json.loads(
            (ROOT / "data/development/qlora_task_conditioned_smoke_v1/manifest.json").read_text(
                encoding="utf-8"
            )
        )
        sealed = json.loads(
            (ROOT / "data/development/t27c_final_smoke_v1/manifest.json").read_text(encoding="utf-8")
        )
        diagnostic = json.loads(
            (ROOT / "data/development/t27c_diagnostic_dev_v1/manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(train["record_count"], 192)
        self.assertGreaterEqual(train["task_example_count"], 256)
        self.assertLessEqual(train["task_example_count"], 512)
        self.assertEqual(sealed["record_count"], 12)
        self.assertEqual(diagnostic["record_count"], 16)
        self.assertEqual(sealed["seal_status"], "sealed")
        self.assertTrue(diagnostic["diagnostic_only"])
        self.assertFalse(diagnostic["valid_for_final_t27c_gate"])
        self.assertEqual(train["split"], "source_train")
        self.assertEqual(sealed["split"], "source_dev")
        self.assertEqual(diagnostic["split"], "source_dev")

    def test_no_forbidden_or_historical_ids(self) -> None:
        train_ids = _ids(ROOT / "data/development/qlora_task_conditioned_smoke_v1/manifest.json")
        sealed_ids = _ids(ROOT / "data/development/t27c_final_smoke_v1/manifest.json")
        diagnostic_ids = _ids(ROOT / "data/development/t27c_diagnostic_dev_v1/manifest.json")
        all_ids = train_ids | sealed_ids | diagnostic_ids
        self.assertFalse(all_ids & set(JOB6059_VAL_IDS))
        self.assertFalse(all_ids & set(T27B_DIAGNOSTIC_IDS))
        self.assertFalse(all_ids & set(T27B_SEALED_IDS))
        self.assertFalse(all_ids & set(HISTORICAL_FORBIDDEN_IDS))
        for rid in all_ids:
            self.assertIsNone(CALIBRATION_ID_RE.match(rid))
            self.assertFalse(any(p.match(rid) for p in FUTURE_MANUAL_ID_RES))

    def test_no_overlap_across_t27c_sets(self) -> None:
        train_ids = _ids(ROOT / "data/development/qlora_task_conditioned_smoke_v1/manifest.json")
        sealed_ids = _ids(ROOT / "data/development/t27c_final_smoke_v1/manifest.json")
        diagnostic_ids = _ids(ROOT / "data/development/t27c_diagnostic_dev_v1/manifest.json")
        self.assertFalse(train_ids & sealed_ids)
        self.assertFalse(train_ids & diagnostic_ids)
        self.assertFalse(sealed_ids & diagnostic_ids)
        train_g = _groups(
            ROOT / "data/development/qlora_task_conditioned_smoke_v1/source_records.jsonl"
        )
        sealed_g = _groups(ROOT / "data/development/t27c_final_smoke_v1/records.jsonl")
        diagnostic_g = _groups(ROOT / "data/development/t27c_diagnostic_dev_v1/records.jsonl")
        self.assertFalse(train_g & sealed_g)
        self.assertFalse(train_g & diagnostic_g)
        self.assertFalse(sealed_g & diagnostic_g)

    def test_sealed_matrix_and_hashes(self) -> None:
        matrix = json.loads(
            (ROOT / "data/development/t27c_final_smoke_v1/required_task_matrix.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("matrix_hash", matrix)
        sealed = json.loads(
            (ROOT / "data/development/t27c_final_smoke_v1/manifest.json").read_text(encoding="utf-8")
        )
        hashes = json.loads(
            (ROOT / "data/development/t27c_final_smoke_v1/hashes.json").read_text(encoding="utf-8")
        )
        self.assertEqual(sealed["manifest_hash"], hashes["manifest_hash"])
        self.assertEqual(len(sealed["record_ids"]), 12)


if __name__ == "__main__":
    unittest.main()
