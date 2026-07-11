"""CPU-only tests for T12 Stage D-Final smoke CLI."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "scripts/t12_run_d_final_smoke.py"
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _load_cli_module():
    spec = importlib.util.spec_from_file_location("t12_run_d_final_smoke", CLI)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class T12DFinalSmokeCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cli_source = CLI.read_text(encoding="utf-8")

    def test_help_works_without_heavy_imports(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(CLI), "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONPATH": "src"},
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("--config", completed.stdout)
        self.assertIn("--source-identity-manifest", completed.stdout)
        self.assertIn("--source-archive", completed.stdout)
        self.assertIn("--slurm-log-path", completed.stdout)

    def test_invalid_config_fails_before_heavy_imports(self) -> None:
        module = _load_cli_module()
        with patch(
            "ambiguity_manager.model.cluster.generation_pipeline_runner.load_d_final_config",
            side_effect=RuntimeError("invalid config"),
        ):
            with self.assertRaises(RuntimeError):
                module.main(
                    [
                        "--config",
                        "missing.json",
                        "--run-dir",
                        "runs/test",
                        "--preflight-result",
                        str(REPO_ROOT / "configs/model/immutable_selection.json"),
                        "--source-identity-manifest",
                        str(REPO_ROOT / "configs/model/immutable_selection.json"),
                        "--source-archive",
                        str(REPO_ROOT / "configs/model/immutable_selection.json"),
                        "--slurm-log-path",
                        "/cluster/logs/t12-d-final-smoke.log",
                        "--measurement-timestamp",
                        "2026-07-11T22:00:00Z",
                    ]
                )

    def test_no_cluster_execution_in_tests(self) -> None:
        self.assertNotIn("ssh", self.cli_source.lower())
        self.assertNotIn("sbatch", self.cli_source.lower())
        self.assertNotIn("apptainer", self.cli_source.lower())
        self.assertNotIn("srun", self.cli_source.lower())

    def test_main_guard_exists(self) -> None:
        self.assertIn('if __name__ == "__main__":', self.cli_source)

    def test_cli_delegates_to_runner(self) -> None:
        module = _load_cli_module()
        blocked = {
            "status": "BLOCKED",
            "run_id": "run-test",
            "rejection_reasons": ["test"],
            "run_dir": "runs/run-test",
            "engine_started": False,
            "response_mode": None,
            "accepted_count": 0,
            "rejected_after_attempts_count": 0,
            "rejected_non_retryable_count": 0,
            "semantic_correctness_status": "not_evaluated",
        }
        with patch(
            "ambiguity_manager.model.cluster.generation_pipeline_runner.run_d_final_smoke",
            return_value=type("Result", (), {"to_dict": lambda self: blocked, **blocked})(),
        ):
            exit_code = module.main(
                [
                    "--config",
                    str(REPO_ROOT / "configs/cluster/t12_d_final_smoke.json"),
                    "--run-dir",
                    "runs/run-test",
                    "--preflight-result",
                    str(REPO_ROOT / "configs/model/immutable_selection.json"),
                    "--source-identity-manifest",
                    str(REPO_ROOT / "configs/model/immutable_selection.json"),
                    "--source-archive",
                    str(REPO_ROOT / "configs/model/immutable_selection.json"),
                    "--slurm-log-path",
                    "/cluster/logs/t12-d-final-smoke.log",
                    "--measurement-timestamp",
                    "2026-07-11T22:00:00Z",
                ]
            )
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
