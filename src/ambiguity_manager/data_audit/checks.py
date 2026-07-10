"""Filesystem and integrity checks for dataset audit."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ambiguity_manager.data_audit.models import (
    CODE_FILE_SUFFIXES,
    CODE_TOOLING_FILENAMES,
    PACKAGE_JSON_MARKERS,
    DuplicateCheckResult,
    OverlapCheckResult,
)


def is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(64)
    except OSError:
        return False
    return head.startswith(b"version https://git-lfs.github.com/spec/v1")


def _is_dataset_payload_file(path: Path) -> bool:
    """Return True when a file is an episode/table payload rather than package metadata."""
    suffix = path.suffix.lower()
    posix = path.as_posix().replace("\\", "/")
    if any(marker in posix for marker in PACKAGE_JSON_MARKERS):
        return False
    if path.name.endswith(".game.json"):
        return True
    if suffix in {".arrow", ".parquet", ".parq"}:
        return True
    if suffix in {".csv", ".tsv", ".jsonl"}:
        return True
    if suffix == ".json":
        return "/data/" in posix or "/games/" in posix or path.parent.name == "data"
    return False


def is_code_only_tree(root: Path, *, episode_glob: str = "*.game.json") -> bool:
    """Detect repositories with code/download tooling but no local episode payload."""
    if not root.is_dir():
        return False
    if list(root.rglob(episode_glob)):
        return False
    payload_files = [
        path
        for path in root.rglob("*")
        if path.is_file() and _is_dataset_payload_file(path)
    ]
    if payload_files:
        return False
    has_download_tooling = any(
        path.name in CODE_TOOLING_FILENAMES for path in root.rglob("*") if path.is_file()
    )
    has_code = any(
        path.suffix.lower() in CODE_FILE_SUFFIXES for path in root.rglob("*") if path.is_file()
    )
    return has_download_tooling and has_code


def classify_payload_verification_status(
    *,
    decision: str,
    excluded: bool,
    blocked: bool,
    payload_readable: bool,
    metadata_only: bool,
    has_warnings: bool,
) -> str:
    if excluded or decision == "exclude":
        return "excluded"
    if metadata_only and not payload_readable:
        return "metadata_only"
    if blocked:
        return "blocked"
    if has_warnings:
        return "partially_verified"
    if payload_readable:
        return "verified"
    return "blocked"


def classify_mapping_verification_status(mapping_risks: list[dict[str, str]]) -> str:
    return "TODO_VERIFY" if mapping_risks else "verified"


def classify_verification_status(
    *,
    decision: str,
    excluded: bool,
    blocked: bool,
    payload_readable: bool,
    metadata_only: bool,
    has_warnings: bool,
    needs_verification: bool,
) -> str:
    """Backward-compatible alias for payload verification classification."""
    _ = needs_verification
    return classify_payload_verification_status(
        decision=decision,
        excluded=excluded,
        blocked=blocked,
        payload_readable=payload_readable,
        metadata_only=metadata_only,
        has_warnings=has_warnings,
    )


def is_metadata_only_tree(root: Path) -> bool:
    if not root.is_dir():
        return False
    files = [path for path in root.rglob("*") if path.is_file()]
    if not files:
        return True
    data_like = [
        path
        for path in files
        if _is_dataset_payload_file(path) and path.name != "dataset_info.json"
    ]
    metadata_only = all(path.name.endswith("dataset_info.json") for path in data_like) if data_like else False
    json_files = [path for path in files if path.suffix.lower() == ".json"]
    return not data_like and bool(json_files) and metadata_only or (
        not data_like and any(path.name == "dataset_info.json" for path in json_files)
    )


def read_hf_metadata_count(metadata_path: Path) -> int | None:
    if not metadata_path.is_file():
        return None
    try:
        with metadata_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    splits = payload.get("splits")
    if isinstance(splits, dict):
        for value in splits.values():
            if isinstance(value, dict) and "num_examples" in value:
                return int(value["num_examples"])
    split_list = payload.get("dataset_info", {}).get("splits")
    if isinstance(split_list, list) and split_list:
        first = split_list[0]
        if isinstance(first, dict) and "num_examples" in first:
            return int(first["num_examples"])
    return payload.get("splits", {}).get("train", {}).get("num_examples") if False else None


def load_dataset_info_num_examples(metadata_path: Path, split_name: str | None = None) -> int | None:
    if not metadata_path.is_file():
        return None
    try:
        with metadata_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    splits = payload.get("splits")
    if isinstance(splits, dict):
        if split_name and split_name in splits:
            value = splits[split_name]
            if isinstance(value, dict) and "num_examples" in value:
                return int(value["num_examples"])
        for value in splits.values():
            if isinstance(value, dict) and "num_examples" in value:
                return int(value["num_examples"])
    return None


def check_duplicate_ids_csv(path: Path, id_fields: list[str]) -> DuplicateCheckResult:
    if not id_fields:
        return DuplicateCheckResult(performed=False, status="skipped")
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        seen: set[tuple[str, ...]] = set()
        duplicate_count = 0
        total = 0
        for row in reader:
            total += 1
            key = tuple(row.get(field, "") for field in id_fields)
            if key in seen:
                duplicate_count += 1
            else:
                seen.add(key)
    return DuplicateCheckResult(
        performed=True,
        id_fields=id_fields,
        total_records=total,
        unique_ids=len(seen),
        duplicate_count=duplicate_count,
        status="ok" if duplicate_count == 0 else "warning",
    )


def check_split_overlap_tsv(paths: list[Path], id_fields: list[str]) -> OverlapCheckResult:
    if not id_fields or len(paths) < 2:
        return OverlapCheckResult(performed=False, status="skipped")
    id_sets: list[set[tuple[str, ...]]] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            current: set[tuple[str, ...]] = set()
            for row in reader:
                current.add(tuple(row.get(field, "") for field in id_fields))
            id_sets.append(current)
    overlap = set.intersection(*id_sets) if id_sets else set()
    return OverlapCheckResult(
        performed=True,
        id_fields=id_fields,
        overlap_count=len(overlap),
        status="warning" if overlap else "ok",
    )


def read_submodule_commit(raw_root: Path) -> str | None:
    git_head = raw_root / ".git"
    if git_head.is_file():
        try:
            gitdir_line = git_head.read_text(encoding="utf-8").strip()
            if gitdir_line.startswith("gitdir:"):
                gitdir = Path(gitdir_line.split(":", 1)[1].strip())
                if not gitdir.is_absolute():
                    gitdir = raw_root / gitdir
                head_file = gitdir / "HEAD"
                if head_file.is_file():
                    ref = head_file.read_text(encoding="utf-8").strip()
                    if ref.startswith("ref:"):
                        ref_path = gitdir / ref.split(":", 1)[1].strip()
                        if ref_path.is_file():
                            return ref_path.read_text(encoding="utf-8").strip()
                    return ref
        except OSError:
            return None
    head_file = raw_root / ".git" / "HEAD"
    if head_file.is_file():
        try:
            ref = head_file.read_text(encoding="utf-8").strip()
            if ref.startswith("ref:"):
                ref_path = raw_root / ".git" / ref.split(":", 1)[1].strip()
                if ref_path.is_file():
                    return ref_path.read_text(encoding="utf-8").strip()
            return ref
        except OSError:
            return None
    return None


def classify_verification_status(
    *,
    decision: str,
    excluded: bool,
    blocked: bool,
    payload_readable: bool,
    metadata_only: bool,
    has_warnings: bool,
    needs_verification: bool,
) -> str:
    """Backward-compatible alias for payload verification classification."""
    _ = needs_verification
    return classify_payload_verification_status(
        decision=decision,
        excluded=excluded,
        blocked=blocked,
        payload_readable=payload_readable,
        metadata_only=metadata_only,
        has_warnings=has_warnings,
    )
