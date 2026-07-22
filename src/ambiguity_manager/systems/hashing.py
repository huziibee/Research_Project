"""Shared hashing helpers for systems artefacts."""

from __future__ import annotations

from typing import Any

from ambiguity_manager.annotation.canonical import canonical_json_bytes, sha256_hex, sha256_json

__all__ = ["canonical_json_bytes", "sha256_hex", "sha256_json", "config_hash"]


def config_hash(payload: Any) -> str:
  return sha256_json(payload)
