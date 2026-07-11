"""Tests for T12 cluster environment manifest templates."""

from __future__ import annotations

import json
import unittest

from ambiguity_manager.model.cluster.manifest_schemas import (
    CLUSTER_INFERENCE_ENV_REL,
    CLUSTER_TRAINING_ENV_REL,
    validate_cluster_environment_manifest,
)
from ambiguity_manager.model.environment import (
    CLUSTER_INFERENCE_ENV_REL as ENV_INFERENCE_REL,
    CLUSTER_TRAINING_ENV_REL as ENV_TRAINING_REL,
)
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root
INFERENCE_PATH = ROOT / CLUSTER_INFERENCE_ENV_REL
TRAINING_PATH = ROOT / CLUSTER_TRAINING_ENV_REL


class T12EnvironmentManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inference = json.loads(INFERENCE_PATH.read_text(encoding="utf-8"))
        cls.training = json.loads(TRAINING_PATH.read_text(encoding="utf-8"))

    def test_templates_exist(self) -> None:
        self.assertTrue(INFERENCE_PATH.is_file())
        self.assertTrue(TRAINING_PATH.is_file())

    def test_cluster_platform(self) -> None:
        self.assertEqual(self.inference["platform"], "wits_slurm_cluster")
        self.assertEqual(self.training["platform"], "wits_slurm_cluster")

    def test_environment_identifiers(self) -> None:
        self.assertEqual(self.inference["environment_id"], "t12-cluster-inference")
        self.assertEqual(self.training["environment_id"], "t12-cluster-training")

    def test_validation_passes_for_cluster_templates(self) -> None:
        for manifest in (self.inference, self.training):
            errors = validate_cluster_environment_manifest(manifest)
            self.assertEqual(errors, [], msg="\n".join(errors))

    def test_training_status_planned_unverified(self) -> None:
        self.assertEqual(self.training["environment_status"], "planned_unverified")

    def test_module_constants_match_active_cluster_paths(self) -> None:
        self.assertEqual(ENV_INFERENCE_REL, CLUSTER_INFERENCE_ENV_REL)
        self.assertEqual(ENV_TRAINING_REL, CLUSTER_TRAINING_ENV_REL)


if __name__ == "__main__":
    unittest.main()
