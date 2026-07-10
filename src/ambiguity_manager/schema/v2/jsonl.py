"""JSONL helpers for canonical schema v2 records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ambiguity_manager.io_guard import resolve_writable_path
from ambiguity_manager.schema.v2.errors import SchemaValidationError
from ambiguity_manager.schema.v2.records import (
  CanonicalRecordV2,
  canonical_record_v2_from_dict,
  canonical_record_v2_to_dict,
)
from ambiguity_manager.schema.v2.validation import validate_canonical_record_v2


def read_canonical_jsonl_v2(path: str | Path) -> list[CanonicalRecordV2]:
  """Load, validate, and return v2 canonical records from a JSONL file."""
  records: list[CanonicalRecordV2] = []
  seen_ids: set[str] = set()
  source = Path(path)
  with source.open(encoding="utf-8") as handle:
    for line_number, line in enumerate(handle, start=1):
      stripped = line.strip()
      if not stripped:
        continue
      try:
        payload = json.loads(stripped)
      except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"line {line_number}: invalid JSON") from exc
      record = validate_canonical_record_v2(payload)
      if record.id in seen_ids:
        raise SchemaValidationError(f"duplicate id {record.id!r} in {source}", field="id")
      seen_ids.add(record.id)
      records.append(record)
  return records


def write_canonical_jsonl_v2(path: str | Path, records: Iterable[CanonicalRecordV2]) -> Path:
  """Write v2 canonical records to JSONL using the guarded write API."""
  target = resolve_writable_path(path)
  target.parent.mkdir(parents=True, exist_ok=True)
  with target.open("w", encoding="utf-8") as handle:
    for record in records:
      validate_canonical_record_v2(record)
      handle.write(json.dumps(canonical_record_v2_to_dict(record), ensure_ascii=False))
      handle.write("\n")
  return target
