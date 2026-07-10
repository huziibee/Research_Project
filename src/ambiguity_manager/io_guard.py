"""Guarded write-path resolution protecting the immutable raw data tree.

Scope and limitations:

- This guard protects *project-owned* writes that go through this API.
- It CANNOT prevent arbitrary third-party tools, direct ``open(path, "w")``
  calls, or shell commands from writing under ``data/raw``.
- All later project code that writes files MUST route target paths through
  :func:`resolve_writable_path` (or :func:`assert_writable_path`) so that
  accidental writes into ``data/raw`` are rejected before any I/O occurs.

Path comparison resolves symlinks/junctions and ``..`` traversal via
``Path.resolve()`` and uses case-insensitive matching on Windows.
"""

from __future__ import annotations

import os
from pathlib import Path

from ambiguity_manager.paths import ProjectPaths


class RawDataWriteError(RuntimeError):
    """Raised when a write is attempted inside the immutable ``data/raw`` tree."""


def _is_within(candidate: Path, protected: Path) -> bool:
    """Return True if ``candidate`` is ``protected`` or nested within it.

    Both paths are fully resolved first so that ``..`` traversal and
    symlink/junction indirection cannot bypass the check. Matching is
    case-insensitive on platforms with case-insensitive filesystems.
    """
    candidate_resolved = candidate.resolve()
    protected_resolved = protected.resolve()

    candidate_parts = candidate_resolved.parts
    protected_parts = protected_resolved.parts

    if os.name == "nt":
        candidate_parts = tuple(part.lower() for part in candidate_parts)
        protected_parts = tuple(part.lower() for part in protected_parts)

    if len(candidate_parts) < len(protected_parts):
        return False
    return candidate_parts[: len(protected_parts)] == protected_parts


def resolve_writable_path(target: str | os.PathLike[str]) -> Path:
    """Resolve ``target`` to an absolute path, rejecting writes into ``data/raw``.

    Args:
        target: The intended write location (absolute or relative).

    Returns:
        The fully resolved absolute path, safe for project-owned writes.

    Raises:
        RawDataWriteError: If the resolved path is ``data/raw`` or nested within it.
    """
    paths = ProjectPaths.from_repo_root()
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate

    if _is_within(candidate, paths.data_raw):
        raise RawDataWriteError(
            f"Refusing to write inside the immutable raw data tree: {candidate} "
            f"(resolved under {paths.data_raw})."
        )
    return candidate.resolve()


def assert_writable_path(target: str | os.PathLike[str]) -> Path:
    """Alias of :func:`resolve_writable_path` for call sites that read as an assertion."""
    return resolve_writable_path(target)
