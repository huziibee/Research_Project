"""Deterministic shard planning for T12 cluster batch execution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ambiguity_manager.model.cluster._config_loader import (
    GENERATOR_VERSION,
    SHARD_ASSIGNMENT_METHOD,
    SHARD_PLAN_SCHEMA_VERSION,
    SHARD_PLAN_VERSION,
    deterministic_json_dumps,
)


class ShardPlanningError(ValueError):
    """Raised when shard planning input is invalid."""


@dataclass(frozen=True)
class IndexedRecord:
    ordinal: int
    record_id: str
    record: dict[str, Any]


@dataclass(frozen=True)
class ShardPlan:
    schema_version: str
    plan_version: str
    input_source: str
    input_sha256: str
    record_count: int
    shard_count: int
    assignment_method: str
    shard_record_ids: tuple[tuple[str, ...], ...]
    shard_record_counts: tuple[int, ...]
    shard_input_hashes: tuple[str, ...]
    generator_version: str
    created_timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_version": self.plan_version,
            "input_source": self.input_source,
            "input_sha256": self.input_sha256,
            "record_count": self.record_count,
            "shard_count": self.shard_count,
            "assignment_method": self.assignment_method,
            "shard_record_ids": [list(ids) for ids in self.shard_record_ids],
            "shard_record_counts": list(self.shard_record_counts),
            "shard_input_hashes": list(self.shard_input_hashes),
            "generator_version": self.generator_version,
            "created_timestamp": self.created_timestamp,
        }


def _hash_records(records: Iterable[IndexedRecord]) -> str:
    lines = []
    for item in records:
        payload = {"ordinal": item.ordinal, "record_id": item.record_id, "record": item.record}
        lines.append(deterministic_json_dumps(payload))
    digest = hashlib.sha256()
    for line in lines:
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _hash_input_lines(lines: list[str]) -> str:
    digest = hashlib.sha256()
    for line in lines:
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def load_jsonl_records(
    path: Path,
    *,
    id_field: str,
) -> tuple[list[str], list[IndexedRecord]]:
    raw_lines: list[str] = []
    records: list[IndexedRecord] = []
    seen_ids: set[str] = set()
    for ordinal, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        raw_lines.append(stripped)
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ShardPlanningError(f"malformed_json_line:{ordinal}") from exc
        if not isinstance(record, dict):
            raise ShardPlanningError(f"malformed_record_type:{ordinal}")
        if id_field not in record:
            raise ShardPlanningError(f"missing_id_field:{ordinal}")
        record_id = str(record[id_field])
        if not record_id:
            raise ShardPlanningError(f"empty_record_id:{ordinal}")
        if record_id in seen_ids:
            raise ShardPlanningError(f"duplicate_record_id:{record_id}")
        seen_ids.add(record_id)
        records.append(IndexedRecord(ordinal=len(records), record_id=record_id, record=record))
    return raw_lines, records


def plan_shards_from_records(
    records: list[IndexedRecord],
    *,
    input_source: str,
    input_sha256: str,
    shard_count: int,
    created_timestamp: str,
) -> ShardPlan:
    if shard_count <= 0:
        raise ShardPlanningError("shard_count_must_be_positive")
    if not records and shard_count > 0:
        return ShardPlan(
            schema_version=SHARD_PLAN_SCHEMA_VERSION,
            plan_version=SHARD_PLAN_VERSION,
            input_source=input_source,
            input_sha256=input_sha256,
            record_count=0,
            shard_count=shard_count,
            assignment_method=SHARD_ASSIGNMENT_METHOD,
            shard_record_ids=tuple(() for _ in range(shard_count)),
            shard_record_counts=tuple(0 for _ in range(shard_count)),
            shard_input_hashes=tuple(_hash_records(()) for _ in range(shard_count)),
            generator_version=GENERATOR_VERSION,
            created_timestamp=created_timestamp,
        )

    total = len(records)
    base = total // shard_count
    remainder = total % shard_count
    sizes = [(base + 1 if index < remainder else base) for index in range(shard_count)]

    shard_ids: list[tuple[str, ...]] = []
    shard_hashes: list[str] = []
    cursor = 0
    for size in sizes:
        chunk = records[cursor : cursor + size]
        cursor += size
        shard_ids.append(tuple(item.record_id for item in chunk))
        shard_hashes.append(_hash_records(chunk))

    return ShardPlan(
        schema_version=SHARD_PLAN_SCHEMA_VERSION,
        plan_version=SHARD_PLAN_VERSION,
        input_source=input_source,
        input_sha256=input_sha256,
        record_count=total,
        shard_count=shard_count,
        assignment_method=SHARD_ASSIGNMENT_METHOD,
        shard_record_ids=tuple(shard_ids),
        shard_record_counts=tuple(len(ids) for ids in shard_ids),
        shard_input_hashes=tuple(shard_hashes),
        generator_version=GENERATOR_VERSION,
        created_timestamp=created_timestamp,
    )


def plan_shards_from_jsonl(
    path: Path,
    *,
    id_field: str,
    shard_count: int,
    created_timestamp: str,
    input_source: str | None = None,
) -> ShardPlan:
    raw_lines, records = load_jsonl_records(path, id_field=id_field)
    input_sha256 = _hash_input_lines(raw_lines)
    return plan_shards_from_records(
        records,
        input_source=input_source or str(path),
        input_sha256=input_sha256,
        shard_count=shard_count,
        created_timestamp=created_timestamp,
    )


def plan_to_canonical_json(plan: ShardPlan) -> str:
    return deterministic_json_dumps(plan.to_dict())
