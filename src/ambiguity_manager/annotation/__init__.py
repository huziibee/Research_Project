"""T13/T14A annotation programme package (CPU-only)."""

from __future__ import annotations

from ambiguity_manager.annotation.canonical import canonical_json_bytes, sha256_hex
from ambiguity_manager.annotation.schema import (
  ANNOTATION_SCHEMA_VERSION,
  HANDBOOK_VERSION,
  PACKAGE_VERSION,
  load_annotation_schema,
)

__all__ = [
  "ANNOTATION_SCHEMA_VERSION",
  "HANDBOOK_VERSION",
  "PACKAGE_VERSION",
  "canonical_json_bytes",
  "load_annotation_schema",
  "sha256_hex",
]
