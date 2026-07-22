"""Provenance helpers for system runs and results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ambiguity_manager.systems.hashing import sha256_json


def utc_now_iso() -> str:
  return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_run_provenance(
  *,
  source_commit: str | None,
  run_mode: str,
  system_ids: list[str],
  config_hashes: dict[str, str],
  input_manifest_hash: str | None,
  schema_version: str,
  handbook_version: str | None = None,
  evaluator_version: str | None = None,
  provider_ids: dict[str, str] | None = None,
  synthetic_only: bool = True,
) -> dict[str, Any]:
  payload = {
    "source_commit": source_commit,
    "run_mode": run_mode,
    "system_ids": list(system_ids),
    "config_hashes": dict(config_hashes),
    "input_manifest_hash": input_manifest_hash,
    "schema_version": schema_version,
    "handbook_version": handbook_version,
    "evaluator_version": evaluator_version,
    "provider_ids": dict(provider_ids or {}),
    "synthetic_only": synthetic_only,
    "official_result": False if synthetic_only else None,
    "created_at": utc_now_iso(),
  }
  payload["provenance_hash"] = sha256_json(
    {k: v for k, v in payload.items() if k != "provenance_hash"}
  )
  return payload
