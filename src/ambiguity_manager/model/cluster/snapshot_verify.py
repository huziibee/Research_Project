"""Standard-library Hugging Face Hub snapshot inventory verifier for T12."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ambiguity_manager.model.cluster.identities import _EXPECTED

CANONICAL_REPOSITORY = _EXPECTED["model_repository"]
CANONICAL_REVISION = _EXPECTED["model_revision"]
CANONICAL_RESOLVED_FILES = 15
CANONICAL_RESOLVED_BYTES = 16397461266
CANONICAL_SAFETENSORS_SHARDS = 5

REQUIRED_FILENAMES = (
    "config.json",
    "generation_config.json",
    "model.safetensors.index.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
    "merges.txt",
)

_HUB_SNAPSHOT_SUFFIX = (
    f"hub/models--Qwen--Qwen3-8B/snapshots/{CANONICAL_REVISION}"
)


@dataclass(frozen=True)
class SnapshotExpectations:
    repository: str = CANONICAL_REPOSITORY
    revision: str = CANONICAL_REVISION
    resolved_files: int = CANONICAL_RESOLVED_FILES
    resolved_bytes: int = CANONICAL_RESOLVED_BYTES
    safetensors_shards: int = CANONICAL_SAFETENSORS_SHARDS
    required_filenames: tuple[str, ...] = REQUIRED_FILENAMES


@dataclass(frozen=True)
class SnapshotVerificationResult:
    status: str
    snapshot_path: str
    repository: str
    revision_directory: str
    resolved_file_count: int
    resolved_total_bytes: int
    safetensors_shard_count: int
    broken_symlink_count: int
    sorted_filenames: tuple[str, ...]
    hub_cache_relationship_valid: bool
    rejection_reasons: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "snapshot_path": self.snapshot_path,
            "repository": self.repository,
            "revision_directory": self.revision_directory,
            "resolved_file_count": self.resolved_file_count,
            "resolved_total_bytes": self.resolved_total_bytes,
            "safetensors_shard_count": self.safetensors_shard_count,
            "broken_symlink_count": self.broken_symlink_count,
            "sorted_filenames": list(self.sorted_filenames),
            "hub_cache_relationship_valid": self.hub_cache_relationship_valid,
            "rejection_reasons": list(self.rejection_reasons),
            "warnings": list(self.warnings),
        }


def _normalize_posix(path: Path) -> str:
    return path.as_posix()


def _hub_cache_relationship_valid(snapshot_path: Path) -> bool:
    normalized = _normalize_posix(snapshot_path.resolve())
    return normalized.endswith(_HUB_SNAPSHOT_SUFFIX)


def verify_snapshot(
    snapshot_path: str | Path,
    *,
    expectations: SnapshotExpectations | None = None,
) -> SnapshotVerificationResult:
    """Verify an on-disk Hub snapshot tree without network access."""
    expected = expectations or SnapshotExpectations()
    root = Path(snapshot_path)
    rejections: list[str] = []
    warnings: list[str] = []

    if not root.is_dir():
        return SnapshotVerificationResult(
            status="fail",
            snapshot_path=str(root),
            repository=expected.repository,
            revision_directory=root.name,
            resolved_file_count=0,
            resolved_total_bytes=0,
            safetensors_shard_count=0,
            broken_symlink_count=0,
            sorted_filenames=(),
            hub_cache_relationship_valid=False,
            rejection_reasons=("snapshot_path_not_directory",),
            warnings=(),
        )

    revision_directory = root.name
    if revision_directory != expected.revision:
        rejections.append("revision_directory_mismatch")

    hub_valid = _hub_cache_relationship_valid(root)
    if not hub_valid:
        rejections.append("hub_cache_relationship_invalid")

    broken_symlinks = 0
    resolved_files: list[tuple[str, int]] = []
    safetensors_shards = 0

    for dirpath, _dirnames, filenames in os.walk(root, followlinks=True):
        current = Path(dirpath)
        for name in filenames:
            file_path = current / name
            rel_name = file_path.relative_to(root).as_posix()
            if file_path.is_symlink():
                if not file_path.exists():
                    broken_symlinks += 1
                    continue
            if not file_path.is_file():
                continue
            size = file_path.stat().st_size
            resolved_files.append((rel_name, size))
            if name.endswith(".safetensors"):
                safetensors_shards += 1

    sorted_filenames = tuple(name for name, _size in sorted(resolved_files, key=lambda item: item[0]))
    resolved_count = len(sorted_filenames)
    resolved_bytes = sum(size for _name, size in resolved_files)

    present_top_level = {Path(name).name for name in sorted_filenames if "/" not in name}
    for required in expected.required_filenames:
        if required not in present_top_level:
            rejections.append(f"missing_required_file:{required}")

    if broken_symlinks != 0:
        rejections.append("broken_symlinks_present")
    if resolved_count != expected.resolved_files:
        rejections.append("resolved_file_count_mismatch")
    if resolved_bytes != expected.resolved_bytes:
        rejections.append("resolved_total_bytes_mismatch")
    if safetensors_shards != expected.safetensors_shards:
        rejections.append("safetensors_shard_count_mismatch")

    status = "pass" if not rejections else "fail"
    return SnapshotVerificationResult(
        status=status,
        snapshot_path=str(root.resolve()),
        repository=expected.repository,
        revision_directory=revision_directory,
        resolved_file_count=resolved_count,
        resolved_total_bytes=resolved_bytes,
        safetensors_shard_count=safetensors_shards,
        broken_symlink_count=broken_symlinks,
        sorted_filenames=sorted_filenames,
        hub_cache_relationship_valid=hub_valid,
        rejection_reasons=tuple(rejections),
        warnings=tuple(warnings),
    )
