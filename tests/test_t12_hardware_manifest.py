"""Tests for T12 hardware evidence manifest validation."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.model.hardware import (
    HARDWARE_MANIFEST_REL,
    validate_hardware_manifest,
)
from ambiguity_manager.paths import ProjectPaths

MANIFEST_PATH = ProjectPaths.from_repo_root().root / HARDWARE_MANIFEST_REL


class T12HardwareManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_manifest_file_exists(self) -> None:
        self.assertTrue(MANIFEST_PATH.is_file())

    def test_validation_passes(self) -> None:
        errors = validate_hardware_manifest(self.manifest)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_windows_and_wsl_sections_present(self) -> None:
        self.assertIn("windows_host", self.manifest)
        self.assertIn("wsl2_ubuntu", self.manifest)

    def test_kib_normalisation_system_ram(self) -> None:
        total = self.manifest["windows_host"]["system_ram_total"]
        self.assertEqual(total["raw_unit"], "KiB")
        self.assertEqual(total["normalised_mib"], total["raw_value"] // 1024)

    def test_bytes_normalisation_physical_memory(self) -> None:
        total = self.manifest["windows_host"]["physical_memory_total"]
        self.assertEqual(total["raw_unit"], "bytes")
        self.assertEqual(total["normalised_mib"], total["raw_value"] // (1024 * 1024))

    def test_nvidia_smi_mib_unchanged(self) -> None:
        vram = self.manifest["windows_host"]["gpu"]["vram_total"]
        self.assertEqual(vram["raw_unit"], "MiB")
        self.assertEqual(vram["normalised_mib"], int(vram["raw_value"]))

    def test_cuda_driver_distinct_from_toolkit_and_pytorch(self) -> None:
        win = self.manifest["windows_host"]
        self.assertEqual(win["driver_reported_cuda_version"], "12.3")
        self.assertFalse(win["cuda_toolkit_nvcc_detected"])
        self.assertIsNone(win["pytorch_cuda_build"])
        self.assertIsNone(win["pytorch_cuda_available"])

    def test_no_gpu_uuid_or_username(self) -> None:
        text = MANIFEST_PATH.read_text(encoding="utf-8").lower()
        self.assertNotIn("uuid", text)
        self.assertNotIn("huzii", text)
        self.assertNotIn("c:\\users\\", text)

    def test_rejects_absolute_path_in_manifest(self) -> None:
        bad = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        bad["notes"] = "C:\\Users\\someone\\cache"
        errors = validate_hardware_manifest(bad)
        self.assertTrue(any("absolute" in e.lower() for e in errors))

    def test_laptop_gpu_recorded(self) -> None:
        gpu_name = self.manifest["windows_host"]["gpu"]["name"]
        self.assertIn("RTX 3070", gpu_name)


if __name__ == "__main__":
    unittest.main()
