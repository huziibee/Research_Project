"""Guarded writers for dataset audit outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ambiguity_manager.io_guard import resolve_writable_path


def dumps_audit_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_audit_json(payload: dict[str, Any], target: str | Path) -> Path:
    path = resolve_writable_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_audit_json(payload), encoding="utf-8")
    return path


def write_text_report(content: str, target: str | Path) -> Path:
    path = resolve_writable_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
