"""Source-dataset contamination / overlap checks (normalised text only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from ambiguity_manager.annotation.duplicates import command_key, normalise_text
from ambiguity_manager.paths import ProjectPaths

SOURCE_DATASETS = (
  "ambik",
  "indirect_requests",
  "codraw_icr_v2",
  "vague",
  "clara",
  "clariq",
)


def _iter_jsonl_commands(path: Path) -> Iterable[str]:
  if not path.is_file():
    return
  with path.open(encoding="utf-8") as handle:
    for line in handle:
      line = line.strip()
      if not line:
        continue
      try:
        payload = json.loads(line)
      except json.JSONDecodeError:
        continue
      command = payload.get("command")
      if isinstance(command, str) and command.strip():
        yield command


def load_source_command_index(root: Path | None = None) -> dict[str, list[str]]:
  paths = ProjectPaths(root=root) if root else ProjectPaths.from_repo_root()
  index: dict[str, list[str]] = {}
  for dataset in SOURCE_DATASETS:
    # Prefer schema_v2 interim if present, else legacy interim.
    candidates = [
      paths.data_interim / "schema_v2" / f"{dataset}.jsonl",
      paths.data_interim / f"{dataset}.jsonl",
    ]
    for path in candidates:
      for command in _iter_jsonl_commands(path):
        key = normalise_text(command)
        index.setdefault(key, []).append(f"{dataset}:{path.name}")
      if path.is_file():
        break
  return index


def find_source_overlaps(
  records: list[dict[str, Any]],
  *,
  root: Path | None = None,
  source_index: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
  index = source_index if source_index is not None else load_source_command_index(root)
  overlaps: list[dict[str, Any]] = []
  for record in records:
    key = command_key(record)
    hits = index.get(key, [])
    if hits:
      overlaps.append(
        {
          "record_id": record.get("record_id"),
          "normalised_command": key,
          "source_hits": sorted(set(hits)),
        }
      )
  return overlaps
