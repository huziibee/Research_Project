"""Annotation config loading."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ambiguity_manager.paths import ProjectPaths

HANDBOOK_VERSION = "1.0.0"
ANNOTATION_SCHEMA_VERSION = "1.0.0"
PACKAGE_VERSION = "1.0.0"

GOLD_FIELD_MARKERS = (
  "gold_",
  "adjudicated_gold",
  "final_gold",
)


def _configs_dir(root: Path | None = None) -> Path:
  paths = ProjectPaths.from_repo_root() if root is None else ProjectPaths(root=root)
  return paths.root / "configs" / "annotation"


def load_json_config(name: str, root: Path | None = None) -> dict[str, Any]:
  path = _configs_dir(root) / name
  with path.open(encoding="utf-8") as handle:
    data = json.load(handle)
  if not isinstance(data, dict):
    raise ValueError(f"{name} must be a JSON object")
  return data


@lru_cache(maxsize=4)
def load_annotation_schema(root_str: str | None = None) -> dict[str, Any]:
  root = Path(root_str) if root_str else None
  return load_json_config("annotation_schema_v1.json", root=root)


@lru_cache(maxsize=4)
def load_roles(root_str: str | None = None) -> dict[str, Any]:
  root = Path(root_str) if root_str else None
  return load_json_config("annotation_roles_v1.json", root=root)


@lru_cache(maxsize=4)
def load_intent_taxonomy(root_str: str | None = None) -> dict[str, Any]:
  root = Path(root_str) if root_str else None
  return load_json_config("intent_taxonomy_v1.json", root=root)


@lru_cache(maxsize=4)
def load_route_precedence(root_str: str | None = None) -> dict[str, Any]:
  root = Path(root_str) if root_str else None
  return load_json_config("route_precedence_v1.json", root=root)


@lru_cache(maxsize=4)
def load_design_cells(root_str: str | None = None) -> dict[str, Any]:
  root = Path(root_str) if root_str else None
  return load_json_config("design_cells_v1.json", root=root)


def clear_config_cache() -> None:
  load_annotation_schema.cache_clear()
  load_roles.cache_clear()
  load_intent_taxonomy.cache_clear()
  load_route_precedence.cache_clear()
  load_design_cells.cache_clear()
