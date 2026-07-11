"""Tests for T12 cluster path sanitisation policy."""

from __future__ import annotations

import json
import unittest

from ambiguity_manager.model.cluster.path_policy import scan_forbidden_paths, validate_path_template
from ambiguity_manager.model.cluster.manifest_schemas import (
    CLUSTER_EXECUTION_POLICY_REL,
    CLUSTER_INFERENCE_ENV_REL,
)
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root


class T12ClusterPathPolicyTests(unittest.TestCase):
    def test_env_template_allowed(self) -> None:
        self.assertEqual(validate_path_template("${T12_CLUSTER_ROOT}"), [])

    def test_var_tmp_template_allowed(self) -> None:
        self.assertEqual(
            validate_path_template("/var/tmp/${USER}-apptainer-${SLURM_JOB_ID}"),
            [],
        )

    def test_windows_path_rejected(self) -> None:
        errors = validate_path_template(r"C:\Users\someone\cache")
        self.assertTrue(any("windows" in e for e in errors))

    def test_wsl_mount_rejected(self) -> None:
        errors = validate_path_template("/mnt/c/Users/someone")
        self.assertTrue(any("wsl" in e for e in errors))

    def test_personal_username_rejected(self) -> None:
        errors = validate_path_template("/scratch/huzii/models")
        self.assertTrue(any("username" in e for e in errors))

    def test_generic_inference_config_has_no_personal_paths(self) -> None:
        data = json.loads((ROOT / CLUSTER_INFERENCE_ENV_REL).read_text(encoding="utf-8"))
        errors = scan_forbidden_paths(data)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_execution_policy_has_no_personal_paths(self) -> None:
        data = json.loads((ROOT / CLUSTER_EXECUTION_POLICY_REL).read_text(encoding="utf-8"))
        errors = scan_forbidden_paths(data)
        self.assertEqual(errors, [], msg="\n".join(errors))


if __name__ == "__main__":
    unittest.main()
