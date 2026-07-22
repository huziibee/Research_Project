"""Deterministic record ID helpers."""

from __future__ import annotations

import re

_PARTITION_RE = re.compile(r"^(calibration|main|reserve|handbook_example|synthetic_test)$")


def format_record_id(partition: str, index: int, year: int = 2026) -> str:
  if not _PARTITION_RE.match(partition):
    raise ValueError(f"invalid partition {partition!r}")
  if index < 1:
    raise ValueError("index must be >= 1")
  prefix = {
    "calibration": "cal",
    "main": "main",
    "reserve": "rsv",
    "handbook_example": "hb",
    "synthetic_test": "syn",
  }[partition]
  return f"manual:{year}:{prefix}:{index:04d}"


def parse_record_id(record_id: str) -> tuple[str, int, int]:
  parts = record_id.split(":")
  if len(parts) != 4 or parts[0] != "manual":
    raise ValueError(f"invalid record_id {record_id!r}")
  year = int(parts[1])
  prefix = parts[2]
  index = int(parts[3])
  reverse = {
    "cal": "calibration",
    "main": "main",
    "rsv": "reserve",
    "hb": "handbook_example",
    "syn": "synthetic_test",
  }
  if prefix not in reverse:
    raise ValueError(f"unknown record_id prefix {prefix!r}")
  return reverse[prefix], index, year
