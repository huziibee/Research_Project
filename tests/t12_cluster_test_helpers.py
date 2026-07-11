"""Test helpers for T12 cluster snapshot verification fixtures."""

from __future__ import annotations

from pathlib import Path

from ambiguity_manager.model.cluster.snapshot_verify import (
    CANONICAL_REVISION,
    REQUIRED_FILENAMES,
    SnapshotExpectations,
)


def build_synthetic_snapshot_tree(
    base: Path,
    *,
    revision: str = CANONICAL_REVISION,
    safetensors_shards: int = 5,
    extra_files: int = 2,
    include_broken_symlink: bool = False,
    hub_layout: bool = True,
) -> Path:
    if hub_layout:
        snapshot_root = (
            base
            / "hub"
            / "models--Qwen--Qwen3-8B"
            / "snapshots"
            / revision
        )
    else:
        snapshot_root = base / revision
    snapshot_root.mkdir(parents=True, exist_ok=True)

    for name in REQUIRED_FILENAMES:
        (snapshot_root / name).write_text("{}", encoding="utf-8")

    for index in range(1, safetensors_shards + 1):
        shard_name = f"model-{index:05d}-of-{safetensors_shards:05d}.safetensors"
        (snapshot_root / shard_name).write_bytes(b"x" * 64)

    for index in range(extra_files):
        extra_name = f"extra-{index}.txt"
        (snapshot_root / extra_name).write_text("extra", encoding="utf-8")

    if include_broken_symlink:
        broken = snapshot_root / "broken.link"
        try:
            broken.symlink_to(snapshot_root / "missing.blob")
        except OSError:
            broken.write_text("broken", encoding="utf-8")
            broken.unlink()
            broken.symlink_to(snapshot_root / "missing.blob")

    return snapshot_root


def snapshot_expectations_from_tree(snapshot_root: Path) -> SnapshotExpectations:
    resolved_files = 0
    resolved_bytes = 0
    safetensors = 0
    for path in snapshot_root.iterdir():
        if path.is_symlink() and not path.exists():
            continue
        if path.is_file() or (path.is_symlink() and path.exists()):
            resolved_files += 1
            resolved_bytes += path.stat().st_size
            if path.name.endswith(".safetensors"):
                safetensors += 1
    return SnapshotExpectations(
        resolved_files=resolved_files,
        resolved_bytes=resolved_bytes,
        safetensors_shards=safetensors,
    )
