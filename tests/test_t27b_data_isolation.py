"""T27B data isolation / leakage tests (CPU-only)."""

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
from ambiguity_manager.model.t27b_datasets import JOB6059_VAL_IDS  # noqa: E402


def _ids(path: Path) -> set[str]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return {str(x) for x in manifest["record_ids"]}


def _groups(records_path: Path) -> set[str]:
    groups: set[str] = set()
    for line in records_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            groups.add(str(json.loads(line)["group_key"]))
    return groups


class T27BDataIsolationTests(unittest.TestCase):
    def test_counts_and_multi_dataset_train(self) -> None:
        train = json.loads(
            (ROOT / "data/development/qlora_structured_emission_recovery_v1/manifest.json").read_text(
                encoding="utf-8"
            )
        )
        sealed = json.loads(
            (ROOT / "data/development/t27b_final_smoke_v1/manifest.json").read_text(encoding="utf-8")
        )
        diagnostic = json.loads(
            (ROOT / "data/development/t27b_diagnostic_dev_v1/manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(train["record_count"], 128)
        self.assertEqual(sealed["record_count"], 8)
        self.assertEqual(diagnostic["record_count"], 12)
        self.assertEqual(sealed["seal_status"], "sealed")
        self.assertTrue(diagnostic["diagnostic_only"])
        self.assertFalse(diagnostic["valid_for_final_t27b_gate"])
        datasets = set(train["datasets"])
        self.assertGreaterEqual(len(datasets), 3)
        self.assertTrue({"ambik", "clara", "codraw_icr_v2"} & datasets)
        # Balanced floors
        rows = [
            json.loads(line)
            for line in (
                ROOT / "data/development/qlora_structured_emission_recovery_v1/records.jsonl"
            )
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        from collections import Counter

        counts = Counter(r["source_dataset"] for r in rows)
        for ds in ("ambik", "clara", "codraw_icr_v2"):
            if ds in counts:
                self.assertGreaterEqual(counts[ds], 16)

    def test_no_job6059_or_forbidden_ids(self) -> None:
        train_ids = _ids(ROOT / "data/development/qlora_structured_emission_recovery_v1/manifest.json")
        sealed_ids = _ids(ROOT / "data/development/t27b_final_smoke_v1/manifest.json")
        diagnostic_ids = _ids(ROOT / "data/development/t27b_diagnostic_dev_v1/manifest.json")
        all_ids = train_ids | sealed_ids | diagnostic_ids
        self.assertFalse(all_ids & set(JOB6059_VAL_IDS))
        for rid in all_ids:
            self.assertIsNone(CALIBRATION_ID_RE.match(rid))
            self.assertFalse(any(p.match(rid) for p in FUTURE_MANUAL_ID_RES))

    def test_no_overlap_across_t27b_sets(self) -> None:
        train_ids = _ids(ROOT / "data/development/qlora_structured_emission_recovery_v1/manifest.json")
        sealed_ids = _ids(ROOT / "data/development/t27b_final_smoke_v1/manifest.json")
        diagnostic_ids = _ids(ROOT / "data/development/t27b_diagnostic_dev_v1/manifest.json")
        self.assertFalse(train_ids & sealed_ids)
        self.assertFalse(train_ids & diagnostic_ids)
        self.assertFalse(sealed_ids & diagnostic_ids)
        train_g = _groups(
            ROOT / "data/development/qlora_structured_emission_recovery_v1/records.jsonl"
        )
        sealed_g = _groups(ROOT / "data/development/t27b_final_smoke_v1/records.jsonl")
        diagnostic_g = _groups(ROOT / "data/development/t27b_diagnostic_dev_v1/records.jsonl")
        self.assertFalse(train_g & sealed_g)
        self.assertFalse(train_g & diagnostic_g)
        self.assertFalse(sealed_g & diagnostic_g)

    def test_supervision_density_above_floor(self) -> None:
        density = json.loads(
            (
                ROOT
                / "data/development/qlora_structured_emission_recovery_v1/supervision_density_report.json"
            ).read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(float(density["mean_supervised_token_percentage"]), 12.0)


if __name__ == "__main__":
    unittest.main()
