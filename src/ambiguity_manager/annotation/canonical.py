"""Canonical JSON helpers for annotation artefacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_bytes(payload: Any) -> bytes:
  return json.dumps(
    payload,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
  ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
  return hashlib.sha256(data).hexdigest()


def sha256_json(payload: Any) -> str:
  return sha256_hex(canonical_json_bytes(payload))


def loads_json(text: str) -> Any:
  return json.loads(text)


def dumps_jsonl_record(payload: dict[str, Any]) -> str:
  return canonical_json_bytes(payload).decode("utf-8")
