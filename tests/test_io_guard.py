"""Tests for guarded writable-path resolution.

Uses the standard-library ``unittest`` framework. Run with
``python -m unittest``.

Note: ``io_guard`` protects project-owned writes that go through this API. It
cannot prevent arbitrary third-party or direct filesystem writes.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ambiguity_manager.io_guard import (
    RawDataWriteError,
    assert_writable_path,
    resolve_writable_path,
)
from ambiguity_manager.paths import ProjectPaths


class IoGuardTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        (self.tmp_path / "pyproject.toml").write_text(
            "[project]\nname = 'tmp'\n", encoding="utf-8"
        )
        patcher = mock.patch(
            "ambiguity_manager.paths.repo_root",
            return_value=self.tmp_path.resolve(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.paths = ProjectPaths.from_repo_root()
        self.paths.ensure_project_dirs()

    def tearDown(self) -> None:
        self._tmp.cleanup()


class RawRejectionTests(IoGuardTestBase):
    def test_rejects_data_raw_itself(self) -> None:
        with self.assertRaises(RawDataWriteError):
            resolve_writable_path(self.paths.data_raw)

    def test_rejects_nested_raw_path(self) -> None:
        target = self.paths.data_raw / "AmbiK" / "out.csv"
        with self.assertRaises(RawDataWriteError):
            resolve_writable_path(target)

    def test_rejects_dotdot_traversal_into_raw(self) -> None:
        target = self.paths.data_interim / ".." / "raw" / "x.txt"
        with self.assertRaises(RawDataWriteError):
            resolve_writable_path(target)

    def test_rejects_relative_path_into_raw(self) -> None:
        cwd = os.getcwd()
        os.chdir(self.paths.root)
        try:
            with self.assertRaises(RawDataWriteError):
                resolve_writable_path(Path("data/raw/foo.txt"))
        finally:
            os.chdir(cwd)

    def test_rejects_absolute_path_into_raw(self) -> None:
        target = (self.paths.data_raw / "absolute.csv").resolve()
        with self.assertRaises(RawDataWriteError):
            resolve_writable_path(target)

    @unittest.skipUnless(sys.platform == "win32", "Windows case-insensitivity check")
    def test_windows_case_variations(self) -> None:
        upper = Path(str(self.paths.data_raw).replace("raw", "RAW"))
        with self.assertRaises(RawDataWriteError):
            resolve_writable_path(upper / "case.csv")

    @unittest.skipUnless(os.name == "nt", "Windows junction test")
    def test_symlink_or_junction_into_raw(self) -> None:
        link_parent = self.paths.data_interim / "link_parent"
        link_parent.mkdir(parents=True, exist_ok=True)
        junction = link_parent / "to_raw"
        try:
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(self.paths.data_raw)],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("Could not create junction for raw-path guard test")
        with self.assertRaises(RawDataWriteError):
            resolve_writable_path(junction / "linked.txt")


class AllowedWriteTests(IoGuardTestBase):
    def test_allows_data_raw_backup(self) -> None:
        target = self.paths.root / "data" / "raw_backup" / "file.txt"
        self.assertEqual(resolve_writable_path(target), target.resolve())

    def test_allows_outputs_and_interim(self) -> None:
        out_target = self.paths.outputs / "metrics" / "x.json"
        interim_target = self.paths.data_interim / "x.csv"
        self.assertEqual(resolve_writable_path(out_target), out_target.resolve())
        self.assertEqual(resolve_writable_path(interim_target), interim_target.resolve())

    def test_assert_writable_path_returns_resolved(self) -> None:
        target = self.paths.outputs / "ok.txt"
        self.assertEqual(assert_writable_path(target), target.resolve())

    def test_guard_is_write_oriented_read_paths_untouched(self) -> None:
        read_target = self.paths.data_raw / "read_only.csv"
        self.assertTrue(
            read_target.resolve().is_relative_to(self.paths.data_raw.resolve())
        )


if __name__ == "__main__":
    unittest.main()
