"""JSONL helpers for canonical dataset records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ambiguity_manager.io_guard import resolve_writable_path
from ambiguity_manager.schema.errors import SchemaValidationError
from ambiguity_manager.schema.records import (
  CanonicalRecord,
  canonical_record_from_dict,
  canonical_record_to_dict,
)
from ambiguity_manager.schema.validation import validate_canonical_record


def read_canonical_jsonl(path: str | Path) -> list[CanonicalRecord]:
  """Load, validate, and return canonical records from a JSONL file."""
  records: list[CanonicalRecord] = []
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
      record = validate_canonical_record(payload)
      if record.id in seen_ids:
        raise SchemaValidationError(f"duplicate id {record.id!r} in {source}", field="id")
      seen_ids.add(record.id)
      records.append(record)
  return records


def write_canonical_jsonl(path: str | Path, records: Iterable[CanonicalRecord]) -> Path:
  """Write canonical records to JSONL using the guarded write API."""
  target = resolve_writable_path(path)
  target.parent.mkdir(parents=True, exist_ok=True)
  with target.open("w", encoding="utf-8") as handle:
    for record in records:
      validate_canonical_record(record)
      handle.write(json.dumps(canonical_record_to_dict(record), ensure_ascii=False))
      handle.write("\n")
  return target
