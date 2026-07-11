"""CPU tests for T12 cluster runtime preflight."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ambiguity_manager.model.cluster.identities import _EXPECTED
from ambiguity_manager.model.cluster.preflight import run_preflight
from ambiguity_manager.model.cluster.snapshot_verify import SnapshotExpectations
from ambiguity_manager.paths import ProjectPaths
from tests.t12_cluster_test_helpers import build_synthetic_snapshot_tree, snapshot_expectations_from_tree

ROOT = ProjectPaths.from_repo_root().root
CONTAINER_SHA = _EXPECTED["container_sha256"]
CONTAINER_SIZE = _EXPECTED["container_size_bytes"]
MODEL_REVISION = _EXPECTED["model_revision"]


def _valid_runtime_facts(snapshot_path: str) -> dict:
    return {
        "timestamp": "2026-07-11T18:00:00Z",
        "allocated_hostname": "mscluster110",
        "partition": "biggpu",
        "exclusive_allocation_confirmed": True,
        "gpu_name": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
        "vram_mib": 97887,
        "compute_capability": "12.0",
        "driver_version": "595.71.05",
        "cuda_available": True,
        "container_path": "${T12_CONTAINER_SIF}",
        "container_size_bytes": CONTAINER_SIZE,
        "container_sha_verification_method": "full_sha256",
        "observed_container_sha256": CONTAINER_SHA,
        "model_repository": _EXPECTED["model_repository"],
        "model_revision": MODEL_REVISION,
        "snapshot_path": snapshot_path,
        "offline_resolution_passed": True,
        "effective_hf_home": "${T12_HF_CACHE}",
        "effective_hub_cache": "${T12_HF_CACHE}/hub",
        "network_fallback": False,
    }


class T12ClusterPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        base = Path(self._tmpdir.name)
        self.snapshot_root = build_synthetic_snapshot_tree(base)
        self.expectations = snapshot_expectations_from_tree(self.snapshot_root)

    def _run(self, facts: dict) -> dict:
        result = run_preflight(
            facts,
            repo_root=ROOT,
            snapshot_expectations=self.expectations,
        )
        return result.to_dict()

    def test_valid_blackwell_runtime_passes(self) -> None:
        result = self._run(_valid_runtime_facts(str(self.snapshot_root)))
        self.assertEqual(result["status"], "pass", msg=json.dumps(result, indent=2))

    def test_wrong_partition_fails(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["partition"] = "gpu"
        result = self._run(facts)
        self.assertEqual(result["status"], "fail")
        self.assertIn("partition_mismatch", result["rejection_reasons"])

    def test_non_exclusive_allocation_fails(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["exclusive_allocation_confirmed"] = False
        result = self._run(facts)
        self.assertIn("exclusive_allocation_not_confirmed", result["rejection_reasons"])

    def test_unapproved_gpu_fails(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["gpu_name"] = "NVIDIA GeForce GTX 1050"
        result = self._run(facts)
        self.assertIn("unapproved_gpu", result["rejection_reasons"])

    def test_insufficient_vram_fails(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["vram_mib"] = 1000
        result = self._run(facts)
        self.assertIn("insufficient_vram", result["rejection_reasons"])

    def test_insufficient_compute_capability_fails(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["compute_capability"] = "8.6"
        result = self._run(facts)
        self.assertIn("insufficient_compute_capability", result["rejection_reasons"])

    def test_denied_node_fails(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        configs = __import__(
            "ambiguity_manager.model.cluster._config_loader",
            fromlist=["load_preflight_configs"],
        ).load_preflight_configs(root=ROOT)
        policy = dict(configs["execution_policy"])
        policy["node_denylist"] = ["mscluster110"]
        with patch(
            "ambiguity_manager.model.cluster.preflight.load_preflight_configs",
            return_value={**configs, "execution_policy": policy},
        ):
            result = run_preflight(
                facts,
                repo_root=ROOT,
                snapshot_expectations=self.expectations,
            ).to_dict()
        self.assertIn("denied_node", result["rejection_reasons"])

    def _run_with_policy(self, facts: dict, policy_overrides: dict) -> dict:
        configs = __import__(
            "ambiguity_manager.model.cluster._config_loader",
            fromlist=["load_preflight_configs"],
        ).load_preflight_configs(root=ROOT)
        policy = dict(configs["execution_policy"])
        policy.update(policy_overrides)
        with patch(
            "ambiguity_manager.model.cluster.preflight.load_preflight_configs",
            return_value={**configs, "execution_policy": policy},
        ):
            return run_preflight(
                facts,
                repo_root=ROOT,
                snapshot_expectations=self.expectations,
            ).to_dict()

    def test_empty_allowlist_accepts_valid_non_denied_node(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["allocated_hostname"] = "mscluster111"
        result = self._run_with_policy(facts, {"node_allowlist": [], "node_denylist": []})
        self.assertEqual(result["status"], "pass", msg=json.dumps(result, indent=2))

    def test_empty_allowlist_does_not_require_specific_nodes(self) -> None:
        for hostname in ("mscluster110", "mscluster111", "mscluster112"):
            with self.subTest(hostname=hostname):
                facts = _valid_runtime_facts(str(self.snapshot_root))
                facts["allocated_hostname"] = hostname
                result = self._run_with_policy(facts, {"node_allowlist": [], "node_denylist": []})
                self.assertEqual(result["status"], "pass", msg=json.dumps(result, indent=2))
                self.assertNotIn("node_allowlist_mismatch", result["rejection_reasons"])

    def test_singleton_allowlist_accepts_listed_node(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["allocated_hostname"] = "mscluster110"
        result = self._run_with_policy(
            facts,
            {"node_allowlist": ["mscluster110"], "node_denylist": []},
        )
        self.assertEqual(result["status"], "pass", msg=json.dumps(result, indent=2))

    def test_singleton_allowlist_rejects_unlisted_node(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["allocated_hostname"] = "mscluster111"
        result = self._run_with_policy(
            facts,
            {"node_allowlist": ["mscluster110"], "node_denylist": []},
        )
        self.assertIn("node_allowlist_mismatch", result["rejection_reasons"])

    def test_multi_node_allowlist_accepts_every_listed_node(self) -> None:
        allowlist = ["mscluster110", "mscluster111", "mscluster112"]
        for hostname in allowlist:
            with self.subTest(hostname=hostname):
                facts = _valid_runtime_facts(str(self.snapshot_root))
                facts["allocated_hostname"] = hostname
                result = self._run_with_policy(
                    facts,
                    {"node_allowlist": allowlist, "node_denylist": []},
                )
                self.assertEqual(result["status"], "pass", msg=json.dumps(result, indent=2))

    def test_multi_node_allowlist_rejects_unlisted_node(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["allocated_hostname"] = "mscluster999"
        result = self._run_with_policy(
            facts,
            {"node_allowlist": ["mscluster110", "mscluster111"], "node_denylist": []},
        )
        self.assertIn("node_allowlist_mismatch", result["rejection_reasons"])

    def test_denylist_overrides_empty_allowlist(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        result = self._run_with_policy(
            facts,
            {"node_allowlist": [], "node_denylist": ["mscluster110"]},
        )
        self.assertIn("denied_node", result["rejection_reasons"])

    def test_denylist_overrides_matching_allowlist_entry(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["allocated_hostname"] = "mscluster110"
        result = self._run_with_policy(
            facts,
            {"node_allowlist": ["mscluster110"], "node_denylist": ["mscluster110"]},
        )
        self.assertIn("denied_node", result["rejection_reasons"])
        self.assertNotIn("node_allowlist_mismatch", result["rejection_reasons"])

    def test_active_execution_policy_has_empty_allowlist(self) -> None:
        policy = json.loads((ROOT / "configs/model/cluster_execution_policy.json").read_text(encoding="utf-8"))
        self.assertEqual(policy["node_allowlist"], [])

    def test_production_preflight_has_no_hardcoded_node_names(self) -> None:
        source = (ROOT / "src/ambiguity_manager/model/cluster/preflight.py").read_text(encoding="utf-8")
        for hostname in ("mscluster110", "mscluster111", "mscluster112"):
            self.assertNotIn(hostname, source)

    def test_empty_allowlist_does_not_require_one_node(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        result = self._run(facts)
        self.assertNotIn("exact_node_required_by_allowlist", result["rejection_reasons"])
        self.assertNotIn("node_allowlist_mismatch", result["rejection_reasons"])

    def test_wrong_model_revision_fails(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["model_revision"] = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
        result = self._run(facts)
        self.assertIn("model_revision_mismatch", result["rejection_reasons"])

    def test_wrong_container_size_fails(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["container_size_bytes"] = 1
        result = self._run(facts)
        self.assertIn("container_size_mismatch", result["rejection_reasons"])

    def test_sidecar_only_hash_fails_integrity_gate(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["container_sha_verification_method"] = "sidecar_sha256"
        facts["observed_container_sha256"] = CONTAINER_SHA
        result = self._run(facts)
        self.assertIn("container_integrity_not_full_sha256", result["rejection_reasons"])

    def test_wrong_full_sha_fails(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["observed_container_sha256"] = "0" * 64
        result = self._run(facts)
        self.assertIn("container_sha256_mismatch", result["rejection_reasons"])

    def test_correct_full_sha_passes(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["container_sha_verification_method"] = "full_sha256"
        facts["observed_container_sha256"] = CONTAINER_SHA
        result = self._run(facts)
        self.assertEqual(result["status"], "pass")

    def test_incorrect_hf_cache_root_fails(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["effective_hub_cache"] = "${T12_HF_CACHE}"
        result = self._run(facts)
        self.assertIn("incorrect_hub_cache", result["rejection_reasons"])

    def test_network_fallback_true_fails(self) -> None:
        facts = _valid_runtime_facts(str(self.snapshot_root))
        facts["network_fallback"] = True
        result = self._run(facts)
        self.assertIn("network_fallback_enabled", result["rejection_reasons"])


if __name__ == "__main__":
    unittest.main()
