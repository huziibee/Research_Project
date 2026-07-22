from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "t16_t24_synthetic"

BANNED_MODULES: tuple[str, ...] = ("torch", "transformers", "vllm", "requests", "httpx", "urllib3")

# Runs in a fresh, isolated (`-I`) interpreter and diffs sys.modules before
# and after importing `module_name`, so the probe reports only modules that
# import actually *pulled in* rather than anything already present for
# unrelated reasons (ambient tooling, pytest plugins, etc.). `-I` also means
# PYTHONPATH is ignored, so SRC is passed as an explicit argv and inserted
# into sys.path inside the child script instead.
_PROBE_SCRIPT = """
import importlib
import json
import sys

sys.path.insert(0, sys.argv[1])
before = set(sys.modules.keys())
importlib.import_module(sys.argv[2])
after = set(sys.modules.keys())
newly_imported = after - before
banned = json.loads(sys.argv[3])
result = {
    name: any(mod == name or mod.startswith(name + ".") for mod in newly_imported)
    for name in banned
}
print(json.dumps(result, sort_keys=True))
"""


def _probe_import(module_name: str, *, banned: tuple[str, ...] = BANNED_MODULES) -> dict[str, bool]:
    completed = subprocess.run(
        [sys.executable, "-I", "-c", _PROBE_SCRIPT, str(SRC), module_name, json.dumps(list(banned))],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
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

    def test_importing_capabilities_module_does_not_import_heavy_ml_stacks(self) -> None:
        probe = _probe_import("ambiguity_manager.systems.capabilities")
        self.assertFalse(probe["torch"])
        self.assertFalse(probe["transformers"])
        self.assertFalse(probe["vllm"])

    def test_importing_model_identities_module_does_not_import_heavy_ml_stacks(self) -> None:
        probe = _probe_import("ambiguity_manager.systems.model_identities")
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

    def test_probe_diffs_newly_imported_modules_not_absolute_presence(self) -> None:
        # A module that is already loaded before the target import (e.g.
        # something importlib pulls in as a side effect of bootstrapping)
        # must not be reported as "newly imported" by the probe. `json` is
        # always loaded by the probe harness itself before the diff is taken,
        # so it is a reliable stand-in for "present but not newly imported".
        probe = _probe_import("ambiguity_manager.systems", banned=("json",))
        self.assertFalse(probe["json"])

    def test_synthetic_fixture_manifest_is_not_t13_calibration_derived(self) -> None:
        manifest = json.loads((FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["source"], "hand_authored_not_t13_calibration")

        t13_dir = ROOT / "data" / "annotations" / "t13"
        if t13_dir.exists():
            self.assertTrue(t13_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
