"""Tests for T12 environment manifest templates."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.model.environment import (
    INFERENCE_ENV_REL,
    TRAINING_ENV_REL,
    validate_environment_manifest,
)
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root
INFERENCE_PATH = ROOT / INFERENCE_ENV_REL
TRAINING_PATH = ROOT / TRAINING_ENV_REL


class T12EnvironmentManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inference = json.loads(INFERENCE_PATH.read_text(encoding="utf-8"))
        cls.training = json.loads(TRAINING_PATH.read_text(encoding="utf-8"))

    def test_templates_exist(self) -> None:
        self.assertTrue(INFERENCE_PATH.is_file())
        self.assertTrue(TRAINING_PATH.is_file())

    def test_wsl2_platform(self) -> None:
        self.assertEqual(self.inference["platform"], "wsl2_ubuntu")
        self.assertEqual(self.training["platform"], "wsl2_ubuntu")

    def test_python_target_311(self) -> None:
        self.assertEqual(self.inference["python_target"], "3.11")
        self.assertEqual(self.training["python_target"], "3.11")

    def test_environment_identifiers(self) -> None:
        self.assertEqual(self.inference["environment_id"], "t12-inference-wsl2")
        self.assertEqual(self.training["environment_id"], "t12-training-wsl2")

    def test_validation_passes_for_current_slice(self) -> None:
        for manifest in (self.inference, self.training):
            if manifest.get("checkpoint_load_verified"):
                slice_number = 3
            elif manifest["environment_status"] != "planned_unverified":
                slice_number = 2
            else:
                slice_number = 1
            errors = validate_environment_manifest(manifest, slice_number=slice_number)
            self.assertEqual(errors, [], msg="\n".join(errors))

    def test_checkpoint_load_verified_after_slice3c(self) -> None:
        self.assertTrue(self.inference["checkpoint_load_verified"])
        self.assertTrue(self.training["checkpoint_load_verified"])
        for manifest in (self.inference, self.training):
            self.assertEqual(manifest["candidate_entry_id"], "t12-cand-001")
            self.assertEqual(manifest["four_bit_load_status"], "passed")

    def test_no_model_identity(self) -> None:
        for manifest in (self.inference, self.training):
            self.assertIsNone(manifest.get("model_id"))
            self.assertIsNone(manifest.get("model_revision"))


if __name__ == "__main__":
    unittest.main()
