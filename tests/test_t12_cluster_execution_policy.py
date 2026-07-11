"""Tests for T12 cluster execution policy configuration."""

from __future__ import annotations

import json
import unittest

from ambiguity_manager.model.cluster.manifest_schemas import (
    CLUSTER_EXECUTION_POLICY_REL,
    validate_cluster_execution_policy,
)
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root


class T12ClusterExecutionPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = json.loads((ROOT / CLUSTER_EXECUTION_POLICY_REL).read_text(encoding="utf-8"))

    def test_required_partition_and_exclusivity(self) -> None:
        self.assertEqual(self.policy["required_partition"], "biggpu")
        self.assertTrue(self.policy["require_exclusive_node"])

    def test_validation_passes(self) -> None:
        errors = validate_cluster_execution_policy(self.policy)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_no_permanent_exact_node_requirement(self) -> None:
        self.assertEqual(self.policy["node_allowlist"], [])

    def test_node_local_temp_template(self) -> None:
        self.assertEqual(
            self.policy["node_local_temp_template"],
            "/var/tmp/${USER}-apptainer-${SLURM_JOB_ID}",
        )

    def test_reject_permanent_single_node_allowlist(self) -> None:
        bad = dict(self.policy)
        bad["node_allowlist"] = ["mscluster112"]
        errors = validate_cluster_execution_policy(bad)
        self.assertTrue(any("exact node" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
