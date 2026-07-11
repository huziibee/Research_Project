"""Tests for dataset licence register governance validation."""

from __future__ import annotations

import json
import unittest

from ambiguity_manager.governance.dataset_licence import (
    T02_HISTORICAL_MANIFEST_REL,
    permission_allows,
    validate_dataset_licence_register,
)
from ambiguity_manager.paths import ProjectPaths


class TestGovernanceDatasetLicence(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.paths = ProjectPaths.from_repo_root()
        cls.register_path = cls.paths.root / "configs" / "licences" / "dataset_licence_register.json"
        with cls.register_path.open(encoding="utf-8") as handle:
            cls.register = json.load(handle)

    def test_register_is_authoritative(self) -> None:
        self.assertEqual(self.register["historical_evidence_manifest"], T02_HISTORICAL_MANIFEST_REL)
        self.assertEqual(self.register["authoritative"], True)

    def test_null_permission_not_true(self) -> None:
        self.assertFalse(permission_allows(None))
        self.assertFalse(permission_allows(False))
        self.assertTrue(permission_allows(True))

    def test_unresolved_blocks_training_and_evaluation(self) -> None:
        for entry in self.register["entries"]:
            if entry["verification_status"] in {"unresolved", "stated_unverified"}:
                self.assertFalse(permission_allows(entry.get("training_permitted")))
                self.assertFalse(permission_allows(entry.get("evaluation_permitted")))
                self.assertFalse(permission_allows(entry.get("redistribution_permitted")))

    def test_verified_without_evidence_rejected(self) -> None:
        bad = json.loads(json.dumps(self.register))
        bad["entries"][0]["verification_status"] = "verified"
        bad["entries"][0]["evidence_path"] = None
        errors = validate_dataset_licence_register(bad)
        self.assertTrue(any("evidence" in e for e in errors))

    def test_manual_compound_present(self) -> None:
        ids = {entry["dataset_id"] for entry in self.register["entries"]}
        self.assertIn("manual_compound", ids)


if __name__ == "__main__":
    unittest.main()
