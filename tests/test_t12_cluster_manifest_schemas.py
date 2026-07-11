"""Tests for T12 cluster manifest schema validation."""

from __future__ import annotations

import json
import unittest

from ambiguity_manager.model.cluster.manifest_schemas import (
    CLUSTER_CHECKPOINT_SNAPSHOT_REL,
    CLUSTER_EXECUTION_POLICY_REL,
    CLUSTER_HARDWARE_EVIDENCE_REL,
    CLUSTER_INFERENCE_ENV_REL,
    CLUSTER_INFERENCE_EVIDENCE_REL,
    CLUSTER_LIVE_VERIFICATION_REL,
    CLUSTER_TRAINING_ENV_REL,
    validate_cluster_checkpoint_snapshot,
    validate_cluster_environment_manifest,
    validate_cluster_execution_policy,
    validate_cluster_hardware_evidence,
    validate_cluster_inference_evidence,
    validate_cluster_live_verification,
)
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root


def _load(relpath: str) -> dict:
    return json.loads((ROOT / relpath).read_text(encoding="utf-8"))


def _execution_policy(**overrides: object) -> dict:
    policy = _load(CLUSTER_EXECUTION_POLICY_REL)
    policy.update(overrides)
    return policy


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

    def test_live_verification_validates(self) -> None:
        data = _load(CLUSTER_LIVE_VERIFICATION_REL)
        errors = validate_cluster_live_verification(data)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_inference_environment_status_verified_live(self) -> None:
        data = _load(CLUSTER_INFERENCE_ENV_REL)
        self.assertEqual(
            data["environment_status"],
            "verified_live_cluster_with_integrity_caveat",
        )

    def test_malformed_snapshot_sha_rejected(self) -> None:
        data = _load(CLUSTER_CHECKPOINT_SNAPSHOT_REL)
        data["model_revision"]["value"] = "bad"
        errors = validate_cluster_checkpoint_snapshot(data)
        self.assertTrue(errors)

    def test_empty_allowlist_is_schema_valid(self) -> None:
        errors = validate_cluster_execution_policy(_execution_policy(node_allowlist=[]))
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_singleton_allowlist_is_schema_valid(self) -> None:
        for node in ("mscluster110", "mscluster112"):
            with self.subTest(node=node):
                errors = validate_cluster_execution_policy(
                    _execution_policy(node_allowlist=[node])
                )
                self.assertEqual(errors, [], msg="\n".join(errors))

    def test_multi_node_allowlist_is_schema_valid(self) -> None:
        errors = validate_cluster_execution_policy(
            _execution_policy(node_allowlist=["mscluster110", "mscluster111"])
        )
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_singleton_denylist_is_schema_valid(self) -> None:
        errors = validate_cluster_execution_policy(
            _execution_policy(node_denylist=["mscluster112"])
        )
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_duplicate_allowlist_entry_rejected(self) -> None:
        errors = validate_cluster_execution_policy(
            _execution_policy(node_allowlist=["mscluster110", "mscluster110"])
        )
        self.assertTrue(any("duplicate" in e for e in errors))

    def test_duplicate_denylist_entry_rejected(self) -> None:
        errors = validate_cluster_execution_policy(
            _execution_policy(node_denylist=["mscluster112", "mscluster112"])
        )
        self.assertTrue(any("duplicate" in e for e in errors))

    def test_blank_allowlist_entry_rejected(self) -> None:
        errors = validate_cluster_execution_policy(_execution_policy(node_allowlist=[""]))
        self.assertTrue(any("blank" in e for e in errors))

    def test_whitespace_padded_allowlist_entry_rejected(self) -> None:
        errors = validate_cluster_execution_policy(
            _execution_policy(node_allowlist=[" mscluster110 "])
        )
        self.assertTrue(any("whitespace" in e for e in errors))

    def test_non_string_allowlist_entry_rejected(self) -> None:
        errors = validate_cluster_execution_policy(_execution_policy(node_allowlist=[110]))
        self.assertTrue(any("non-empty string" in e for e in errors))

    def test_node_present_in_allowlist_and_denylist_rejected(self) -> None:
        errors = validate_cluster_execution_policy(
            _execution_policy(
                node_allowlist=["mscluster110"],
                node_denylist=["mscluster110"],
            )
        )
        self.assertTrue(any("overlap" in e or "contradict" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
