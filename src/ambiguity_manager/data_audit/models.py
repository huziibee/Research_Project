"""Shared types and constants for dataset audit."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

VERIFICATION_STATUSES = frozenset(
    {
        "verified",
        "partially_verified",
        "metadata_only",
        "blocked",
        "excluded",
        "TODO_VERIFY",
    }
)

INCLUSION_DECISIONS = frozenset(
    {"include", "exclude", "conditional", "challenge_only", "auxiliary"}
)

LICENCE_STATUSES = frozenset(
    {"verified", "unresolved", "TODO_VERIFY", "not_applicable", "excluded", "stated_unverified"}
)

CODE_TOOLING_FILENAMES = frozenset({"download_data.sh", "download_data.py"})
CODE_FILE_SUFFIXES = frozenset({".py", ".ipynb", ".sh", ".yaml", ".yml"})
DATA_PAYLOAD_SUFFIXES = frozenset({".arrow", ".parquet", ".parq", ".csv", ".tsv", ".jsonl"})
PACKAGE_JSON_MARKERS = (
    "meta_data_files/",
    "task_definitions/",
    "experiments/",
    "build/",
    ".egg-info/",
)


@dataclass
class ReaderResult:
    ok: bool
    record_count: int = 0
    header_fields: list[str] = field(default_factory=list)
    field_types: dict[str, str] = field(default_factory=dict)
    null_counts: dict[str, int] = field(default_factory=dict)
    error_kind: str | None = None
    error_message: str | None = None
    container_kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DuplicateCheckResult:
    performed: bool
    id_fields: list[str] = field(default_factory=list)
    total_records: int = 0
    unique_ids: int = 0
    duplicate_count: int = 0
    status: str = "skipped"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OverlapCheckResult:
    performed: bool
    id_fields: list[str] = field(default_factory=list)
    overlap_count: int = 0
    status: str = "skipped"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
