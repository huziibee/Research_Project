"""Central repository path configuration.

All project code must derive filesystem locations from this module rather than
hard-coding absolute paths. Paths are resolved relative to the repository root,
which is located by searching upward for ``pyproject.toml``. This keeps the
project portable across machines and works with Windows paths via ``pathlib``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_MARKER = "pyproject.toml"


def repo_root(start: Path | None = None) -> Path:
    """Return the repository root by searching upward for ``pyproject.toml``.

    Args:
        start: Directory or file to start searching from. Defaults to the
            location of this module.

    Raises:
        FileNotFoundError: If no ancestor directory contains ``pyproject.toml``.
    """
    origin = Path(start) if start is not None else Path(__file__)
    origin = origin.resolve()
    candidates = [origin, *origin.parents] if origin.is_file() else [origin, *origin.parents]
    for directory in candidates:
        if (directory / _MARKER).is_file():
            return directory.resolve()
    raise FileNotFoundError(
        f"Could not locate {_MARKER} in {origin} or any parent directory."
    )


@dataclass(frozen=True)
class ProjectPaths:
    """Resolved, repository-relative directories used across the project."""

    root: Path

    @classmethod
    def from_repo_root(cls, start: Path | None = None) -> "ProjectPaths":
        return cls(root=repo_root(start))

    # --- Data locations -------------------------------------------------
    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def data_raw(self) -> Path:
        """Immutable external dataset payloads. Never write here."""
        return self.data / "raw"

    @property
    def data_interim(self) -> Path:
        return self.data / "interim"

    @property
    def data_processed(self) -> Path:
        return self.data / "processed"

    @property
    def data_annotations(self) -> Path:
        return self.data / "annotations"

    @property
    def data_splits(self) -> Path:
        return self.data / "splits"

    # --- Project locations ----------------------------------------------
    @property
    def configs(self) -> Path:
        return self.root / "configs"

    @property
    def docs(self) -> Path:
        return self.root / "docs"

    @property
    def scripts(self) -> Path:
        return self.root / "scripts"

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    @property
    def tests(self) -> Path:
        return self.root / "tests"

    def writable_dirs(self) -> tuple[Path, ...]:
        """Project-owned directories that scaffold creation should ensure."""
        return (
            self.data_interim,
            self.data_processed,
            self.data_annotations,
            self.data_splits,
            self.outputs,
        )

    def ensure_project_dirs(self) -> None:
        """Create the project-owned writable directories if they are missing.

        This never creates or writes anything under ``data/raw``.
        """
        for directory in self.writable_dirs():
            directory.mkdir(parents=True, exist_ok=True)
