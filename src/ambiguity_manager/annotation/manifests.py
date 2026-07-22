"""Deterministic package manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ambiguity_manager.annotation.canonical import sha256_hex, sha256_json
from ambiguity_manager.annotation.packages import package_bytes_hash, record_set_ids
from ambiguity_manager.annotation.schema import (
  ANNOTATION_SCHEMA_VERSION,
  HANDBOOK_VERSION,
  PACKAGE_VERSION,
)


def build_manifest(
  *,
  package_id: str,
  annotator_role: str | None,
  partition: str,
  records: list[dict[str, Any]],
  source_path: str,
  extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
  payload = {
    "package_id": package_id,
    "annotator_role": annotator_role,
    "dataset_partition": partition,
    "n_records": len(records),
    "record_ids": record_set_ids(records),
    "record_order": [str(r["record_id"]) for r in records],
    "package_sha256": package_bytes_hash(records),
    "handbook_version": HANDBOOK_VERSION,
    "annotation_schema_version": ANNOTATION_SCHEMA_VERSION,
    "package_version": PACKAGE_VERSION,
    "source_path": source_path,
    "contains_gold_labels": False,
    "contains_hidden_author_fields": False if annotator_role else None,
  }
  if extra:
    payload.update(extra)
  payload["manifest_sha256"] = sha256_json({k: v for k, v in payload.items() if k != "manifest_sha256"})
  return payload


def write_manifest(path: Path, manifest: dict[str, Any], *, overwrite: bool = False) -> str:
  if path.exists() and not overwrite:
    raise FileExistsError(f"refusing to overwrite frozen manifest: {path}")
  path.parent.mkdir(parents=True, exist_ok=True)
  text = json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
  path.write_text(text, encoding="utf-8")
  return sha256_hex(text.encode("utf-8"))
