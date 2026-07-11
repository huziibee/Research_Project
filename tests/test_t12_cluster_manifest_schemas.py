"""Tests for T12 cluster manifest schema validation."""

from __future__ import annotations

import json
import unittest

from ambiguity_manager.model.cluster.manifest_schemas import (
    CLUSTER_CHECKPOINT_SNAPSHOT_REL,
    CLUSTER_HARDWARE_EVIDENCE_REL,
    CLUSTER_INFERENCE_ENV_REL,
    CLUSTER_INFERENCE_EVIDENCE_REL,
    CLUSTER_TRAINING_ENV_REL,
    validate_cluster_checkpoint_snapshot,
    validate_cluster_environment_manifest,
    validate_cluster_hardware_evidence,
    validate_cluster_inference_evidence,
)
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root


def _load(relpath: str) -> dict:
    return json.loads((ROOT / relpath).read_text(encoding="utf-8"))


class T12ClusterManifestSchemasTests(unittest.TestCase):
    def test_inference_environment_validates(self) -> None:
        data = _load(CLUSTER_INFERENCE_ENV_REL)
        errors = validate_cluster_environment_manifest(data)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_training_manifest_cannot_claim_verified_adapter(self) -> None:
        data = _load(CLUSTER_TRAINING_ENV_REL)
        data["training_stack"]["lora_attach_passed"] = True
        errors = validate_cluster_environment_manifest(data)
        self.assertTrue(any("lora_attach_passed" in e for e in errors))

    def test_training_manifest_status_planned_unverified(self) -> None:
        data = _load(CLUSTER_TRAINING_ENV_REL)
        self.assertEqual(data["environment_status"], "planned_unverified")

    def test_active_inference_does_not_reference_qwen25(self) -> None:
        data = _load(CLUSTER_INFERENCE_ENV_REL)
        text = json.dumps(data)
        self.assertNotIn("Qwen2.5-1.5B", text)

    def test_hardware_evidence_validates(self) -> None:
        data = _load(CLUSTER_HARDWARE_EVIDENCE_REL)
        errors = validate_cluster_hardware_evidence(data)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_inference_evidence_validates(self) -> None:
        data = _load(CLUSTER_INFERENCE_EVIDENCE_REL)
        errors = validate_cluster_inference_evidence(data)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_checkpoint_snapshot_validates(self) -> None:
        data = _load(CLUSTER_CHECKPOINT_SNAPSHOT_REL)
        errors = validate_cluster_checkpoint_snapshot(data)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_malformed_snapshot_sha_rejected(self) -> None:
        data = _load(CLUSTER_CHECKPOINT_SNAPSHOT_REL)
        data["model_revision"]["value"] = "bad"
        errors = validate_cluster_checkpoint_snapshot(data)
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
