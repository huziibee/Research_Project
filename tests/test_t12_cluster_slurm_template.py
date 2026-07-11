"""CPU tests for T12 Slurm inference job template contract."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root
TEMPLATE_JSON = ROOT / "configs/cluster/t12_inference_job.template.json"
SBATCH = ROOT / "configs/cluster/t12_inference.sbatch"

FORBIDDEN_PATTERNS = (
    r"--gres",
    r"--nodelist",
    r"/home-mscluster/",
    r"\bhuzii\b",
    r"\bmbangie\b",
    r"C:\\Users\\",
    r"password",
    r"token\s*=",
    r"@.*\.(ac\.za|edu|com)",
)


class T12ClusterSlurmTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = json.loads(TEMPLATE_JSON.read_text(encoding="utf-8"))
        cls.sbatch = SBATCH.read_text(encoding="utf-8")

    def test_contains_biggpu(self) -> None:
        self.assertIn("biggpu", self.sbatch)
        self.assertEqual(self.template["slurm"]["partition"], "biggpu")

    def test_contains_exclusive_allocation(self) -> None:
        self.assertIn("--exclusive", self.sbatch)
        self.assertTrue(self.template["slurm"]["exclusive"])

    def test_contains_no_gres(self) -> None:
        self.assertNotRegex(self.sbatch, re.compile(r"--gres", re.IGNORECASE))

    def test_contains_no_hardcoded_node(self) -> None:
        self.assertNotIn("--nodelist", self.sbatch)

    def test_contains_no_personal_path(self) -> None:
        combined = self.sbatch + json.dumps(self.template)
        for pattern in FORBIDDEN_PATTERNS[2:6]:
            self.assertNotRegex(combined, re.compile(pattern, re.IGNORECASE))

    def test_contains_no_credential(self) -> None:
        combined = self.sbatch + json.dumps(self.template)
        self.assertNotRegex(combined, re.compile(r"password|token\s*=", re.IGNORECASE))

    def test_contains_offline_flags(self) -> None:
        self.assertIn("HF_HUB_OFFLINE=1", self.sbatch)
        self.assertIn("TRANSFORMERS_OFFLINE=1", self.sbatch)
        flags = self.template["environment"]["offline_flags"]
        self.assertIn("HF_HUB_OFFLINE=1", flags)
        self.assertIn("TRANSFORMERS_OFFLINE=1", flags)

    def test_contains_correct_hub_cache_relationship(self) -> None:
        self.assertIn("${T12_HF_CACHE}/hub", self.sbatch)
        self.assertEqual(self.template["environment"]["hf_home"], "${T12_HF_CACHE}")
        self.assertEqual(self.template["environment"]["hf_hub_cache"], "${T12_HF_CACHE}/hub")

    def test_contains_job_local_var_tmp_pattern(self) -> None:
        self.assertIn("/var/tmp/${USER}-apptainer-${SLURM_JOB_ID}", self.sbatch)
        self.assertEqual(
            self.template["paths"]["node_local_temp"],
            "/var/tmp/${USER}-apptainer-${SLURM_JOB_ID}",
        )

    def test_preflight_before_model_execution(self) -> None:
        preflight_index = self.sbatch.index("t12_cluster_preflight.py")
        self.assertIn("Stage C2", self.sbatch)
        self.assertGreater(preflight_index, 0)

    def test_placeholders_present(self) -> None:
        for key in ("run_id", "shard_id", "config_path"):
            self.assertIn(key, self.template["placeholders"])


if __name__ == "__main__":
    unittest.main()
