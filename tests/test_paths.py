"""Tests for repository path resolution.

Uses the standard-library ``unittest`` framework so the suite runs without
installing third-party dependencies. Run with ``python -m unittest``.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ambiguity_manager.paths import ProjectPaths, repo_root


class RepoRootTests(unittest.TestCase):
    def test_repo_root_finds_pyproject_toml(self) -> None:
        root = repo_root()
        self.assertTrue((root / "pyproject.toml").is_file())

    def test_repo_root_from_nested_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            nested = tmp_path / "a" / "b"
            nested.mkdir(parents=True)
            (tmp_path / "pyproject.toml").write_text(
                "[project]\nname = 'tmp'\n", encoding="utf-8"
            )
            self.assertEqual(repo_root(start=nested), tmp_path.resolve())

    def test_repo_root_raises_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                repo_root(start=Path(tmp))


class ProjectPathsTests(unittest.TestCase):
    def test_standard_paths_are_under_repo_root(self) -> None:
        paths = ProjectPaths.from_repo_root()
        root = paths.root
        self.assertTrue(paths.data_raw.is_relative_to(root))
        self.assertTrue(paths.outputs.is_relative_to(root))
        self.assertTrue(paths.data_interim.is_relative_to(root))
        self.assertTrue(paths.data_processed.is_relative_to(root))
        self.assertTrue(paths.data_annotations.is_relative_to(root))
        self.assertTrue(paths.data_splits.is_relative_to(root))

    def test_paths_are_pathlib_path_objects(self) -> None:
        paths = ProjectPaths.from_repo_root()
        self.assertIsInstance(paths.root, Path)
        self.assertIsInstance(paths.data_raw, Path)

    def test_paths_are_absolute_and_derived_from_root(self) -> None:
        paths = ProjectPaths.from_repo_root()
        root_text = str(paths.root).lower()
        for value in (paths.root, paths.data_raw, paths.outputs, paths.data_interim):
            self.assertTrue(value.is_absolute())
            self.assertTrue(str(value).lower().startswith(root_text))

    def test_ensure_project_dirs_creates_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "pyproject.toml").write_text(
                "[project]\nname = 'tmp'\n", encoding="utf-8"
            )
            with mock.patch(
                "ambiguity_manager.paths.repo_root",
                return_value=tmp_path.resolve(),
            ):
                paths = ProjectPaths.from_repo_root()
                paths.ensure_project_dirs()
                self.assertTrue(paths.outputs.is_dir())
                self.assertTrue(paths.data_interim.is_dir())


if __name__ == "__main__":
    unittest.main()
