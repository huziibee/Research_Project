"""CPU-only validation for T12 cluster operator canary evidence."""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

from ambiguity_manager.model.cluster.path_policy import scan_forbidden_paths
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root
EVIDENCE_REL = "configs/cluster/evidence/t12_cluster_operator_canary.json"
REPORT_REL = "docs/reports/ticket_T12_cluster_operator_canary.md"
LICENCE_REL = "configs/licences/model_licence_register.json"
OPERATOR_SHA = "fe85d8c822fb48f5fea77817b8a99251c61dc378"
ARCHIVE_SHA = "3dafc8e3021b94632926694904ee92a3250ed3cb9be9653e66550f2169fb8388"
RUN_ID = "t12-canary-20260722T060451Z-fe85d8c"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class T12ClusterOperatorCanaryEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = json.loads((ROOT / EVIDENCE_REL).read_text(encoding="utf-8"))
        cls.report = (ROOT / REPORT_REL).read_text(encoding="utf-8")
        cls.licence = json.loads((ROOT / LICENCE_REL).read_text(encoding="utf-8"))

    def test_files_exist(self) -> None:
        self.assertTrue((ROOT / EVIDENCE_REL).is_file())
        self.assertTrue((ROOT / REPORT_REL).is_file())

    def test_operator_and_archive_identity(self) -> None:
        self.assertEqual(self.evidence["operator_commit"]["sha"], OPERATOR_SHA)
        self.assertEqual(self.evidence["source_transfer"]["source_commit_sha"], OPERATOR_SHA)
        self.assertEqual(self.evidence["source_transfer"]["archive_sha256"], ARCHIVE_SHA)
        self.assertRegex(ARCHIVE_SHA, SHA256_RE)
        self.assertEqual(self.evidence["source_transfer"]["method"], "git_archive")

    def test_run_identity(self) -> None:
        run = self.evidence["run_identity"]
        self.assertEqual(run["run_id"], RUN_ID)
        self.assertEqual(run["slurm_job_id"], "4122")
        self.assertEqual(run["partition"], "stampede")
        self.assertEqual(run["node"], "mscluster40")
        self.assertEqual(run["terminal_state"], "COMPLETED")
        self.assertIn("${T12_CLUSTER_ROOT}", run["remote_result_path_template"])
        self.assertTrue(run["local_pull_path"].startswith("outputs/"))

    def test_verification_passed(self) -> None:
        self.assertTrue(self.evidence["verification"]["passed"])
        self.assertEqual(self.evidence["verification"]["errors"], [])

    def test_no_model_gpu_or_protected_data(self) -> None:
        safety = self.evidence["safety_confirmation"]
        self.assertFalse(safety["gpus_required"])
        self.assertFalse(safety["model_loaded"])
        self.assertFalse(safety["protected_data_used"])
        self.assertEqual(safety["forbidden_imports_present"], [])
        self.assertIsNone(self.evidence["selected_model"])
        self.assertIsNone(self.licence.get("selected_model"))

    def test_paths_sanitised(self) -> None:
        errors = scan_forbidden_paths(self.evidence)
        self.assertEqual(errors, [])
        self.assertNotIn("home-mscluster", self.report)
        self.assertNotIn("/home/", self.report)

    def test_no_ml_imports(self) -> None:
        for name in ("torch", "transformers", "vllm"):
            self.assertNotIn(name, sys.modules)


if __name__ == "__main__":
    unittest.main()
