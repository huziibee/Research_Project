"""CPC and string normalisation for deterministic evaluation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ambiguity_manager.paths import ProjectPaths


def load_cpc_normalisation(path: Path | None = None) -> dict[str, Any]:
  if path is None:
    path = ProjectPaths.from_repo_root().configs / "evaluation" / "cpc_normalisation_v1.json"
  return json.loads(path.read_text(encoding="utf-8"))


def normalise_text(value: str | None, rules: dict[str, Any] | None = None) -> str | None:
  if value is None:
    return None
  rules = rules or load_cpc_normalisation().get("rules", {})
  text = value
  if rules.get("strip_whitespace", True):
    text = text.strip()
  if rules.get("lowercase", True):
    text = text.lower()
  if rules.get("collapse_internal_whitespace", True):
    text = re.sub(r"\s+", " ", text)
  if rules.get("drop_trailing_punctuation", True):
    text = re.sub(r"[.,;:!?]+$", "", text)
  return text
