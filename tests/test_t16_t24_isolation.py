from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "t16_t24_synthetic"


def _probe_import(module_name: str) -> dict[str, bool]:
    script = """
import importlib
import json
import sys

importlib.import_module(sys.argv[1])
banned = ["torch", "transformers", "vllm", "requests", "httpx", "urllib3"]
print(json.dumps({name: (name in sys.modules) for name in banned}, sort_keys=True))
"""
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC) if not existing else os.pathsep.join([str(SRC), existing])
    completed = subprocess.run(
        [sys.executable, "-c", script, module_name],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    return json.loads(completed.stdout.strip())


class T16T24IsolationTests(unittest.TestCase):
    def test_importing_systems_package_does_not_import_heavy_ml_stacks(self) -> None:
        probe = _probe_import("ambiguity_manager.systems")
        self.assertFalse(probe["torch"])
        self.assertFalse(probe["transformers"])
        self.assertFalse(probe["vllm"])

    def test_importing_evaluation_package_does_not_import_heavy_ml_stacks(self) -> None:
        probe = _probe_import("ambiguity_manager.evaluation")
        self.assertFalse(probe["torch"])
        self.assertFalse(probe["transformers"])
        self.assertFalse(probe["vllm"])

    def test_importing_execution_module_does_not_import_heavy_ml_stacks(self) -> None:
        probe = _probe_import("ambiguity_manager.systems.execution")
        self.assertFalse(probe["torch"])
        self.assertFalse(probe["transformers"])
        self.assertFalse(probe["vllm"])

    def test_import_probes_do_not_pull_network_client_modules(self) -> None:
        for module_name in (
            "ambiguity_manager.systems",
            "ambiguity_manager.evaluation",
            "ambiguity_manager.systems.execution",
        ):
            probe = _probe_import(module_name)
            self.assertFalse(probe["requests"], msg=module_name)
            self.assertFalse(probe["httpx"], msg=module_name)
            self.assertFalse(probe["urllib3"], msg=module_name)

    def test_synthetic_fixture_manifest_is_not_t13_calibration_derived(self) -> None:
        manifest = json.loads((FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["source"], "hand_authored_not_t13_calibration")

        t13_dir = ROOT / "data" / "annotations" / "t13"
        if t13_dir.exists():
            self.assertTrue(t13_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
