"""CPU-only tests for T12 cluster batch runner CLI and Slurm wiring (Stage C2A)."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root
SBATCH = ROOT / "configs/cluster/t12_inference.sbatch"
TEMPLATE_JSON = ROOT / "configs/cluster/t12_inference_job.template.json"
CLI = ROOT / "scripts/t12_cluster_run_batch.py"


def _load_cli_module():
    spec = importlib.util.spec_from_file_location("t12_cluster_run_batch", CLI)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class T12ClusterRunBatchCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sbatch = SBATCH.read_text(encoding="utf-8")
        cls.template = json.loads(TEMPLATE_JSON.read_text(encoding="utf-8"))
        cls.cli_source = CLI.read_text(encoding="utf-8")

    def test_cli_help_exits_zero(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(CLI), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("preflight-result", completed.stdout)

    def test_main_guard_exists(self) -> None:
        self.assertIn('if __name__ == "__main__":', self.cli_source)

    def test_freeze_support_exists(self) -> None:
        self.assertIn("multiprocessing.freeze_support()", self.cli_source)

    def test_spawn_method_environment_variable_in_sbatch(self) -> None:
        self.assertIn("VLLM_WORKER_MULTIPROC_METHOD=spawn", self.sbatch)

    def test_no_per_record_subprocess_logic_in_cli(self) -> None:
        self.assertNotIn("Popen", self.cli_source)
        self.assertNotIn("subprocess.run", self.cli_source)

    def test_slurm_template_invokes_runner(self) -> None:
        self.assertIn("t12_cluster_run_batch.py", self.sbatch)

    def test_template_contains_no_ssh_command(self) -> None:
        combined = self.sbatch + json.dumps(self.template)
        self.assertNotRegex(combined, re.compile(r"\bssh\b", re.IGNORECASE))

    def test_template_contains_no_personal_path_or_credential(self) -> None:
        combined = self.sbatch + json.dumps(self.template)
        self.assertNotRegex(combined, re.compile(r"/home-mscluster/|password|token\s*=", re.IGNORECASE))

    def test_template_passes_explicit_runner_paths(self) -> None:
        for token in (
            "T12_PREFLIGHT_RESULT_PATH",
            "T12_SHARD_PLAN_PATH",
            "T12_SHARD_ID",
            "T12_RUN_DIR",
            "T12_VLLM_RUNTIME_CONFIG",
        ):
            self.assertIn(token, self.sbatch)
        placeholders = self.template["placeholders"]
        for key in (
            "preflight_result_path",
            "shard_plan_path",
            "shard_id",
            "run_dir",
            "runtime_config_path",
        ):
            self.assertIn(key, placeholders)

    def test_cli_returns_nonzero_for_completed_shard_conflict(self) -> None:
        module = _load_cli_module()
        blocked = {
            "status": "blocked",
            "run_id": "run-001",
            "shard_id": "shard-000",
            "skipped": False,
            "rejection_reasons": ["completed_conflict:input_plan_hash"],
            "manifest_path": None,
            "backend_config_hash": "hash",
            "engine_started": False,
        }
        with patch.object(
            module,
            "run_shard_batch",
            return_value=type("Result", (), {"to_dict": lambda self: blocked, **blocked})(),
        ):
            exit_code = module.main(
                [
                    "--runtime-config",
                    "runtime.json",
                    "--shard-plan",
                    "plan.json",
                    "--shard-id",
                    "shard-000",
                    "--run-dir",
                    "runs/run-001",
                    "--preflight-result",
                    str(ROOT / "configs/model/immutable_selection.json"),
                    "--input-jsonl",
                    "input.jsonl",
                    "--synthetic-declaration",
                    "synthetic.json",
                    "--start-timestamp",
                    "2026-07-11T19:00:00Z",
                    "--end-timestamp",
                    "2026-07-11T19:01:00Z",
                ]
            )
        self.assertEqual(exit_code, 1)

    def test_cli_has_no_force_overwrite_flag(self) -> None:
        self.assertNotIn("--force-overwrite", self.cli_source)
        self.assertNotIn("force_overwrite", self.cli_source)
        self.assertNotIn("identity-bypass", self.cli_source)
        self.assertNotIn("--identity-bypass", self.cli_source)

    def test_cli_allows_retryable_failed_shard_to_proceed(self) -> None:
        module = _load_cli_module()
        failed = {
            "status": "completed",
            "run_id": "run-001",
            "shard_id": "shard-000",
            "skipped": False,
            "rejection_reasons": [],
            "manifest_path": "runs/run-001/shard-000.manifest.json",
            "backend_config_hash": "hash",
            "engine_started": True,
            "decision": "retry_failed",
        }
        with patch.object(
            module,
            "run_shard_batch",
            return_value=type("Result", (), {"to_dict": lambda self: failed, **failed})(),
        ):
            exit_code = module.main(
                [
                    "--runtime-config",
                    "runtime.json",
                    "--shard-plan",
                    "plan.json",
                    "--shard-id",
                    "shard-000",
                    "--run-dir",
                    "runs/run-001",
                    "--preflight-result",
                    str(ROOT / "configs/model/immutable_selection.json"),
                    "--input-jsonl",
                    "input.jsonl",
                    "--synthetic-declaration",
                    "synthetic.json",
                    "--start-timestamp",
                    "2026-07-11T19:00:00Z",
                    "--end-timestamp",
                    "2026-07-11T19:01:00Z",
                ]
            )
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
