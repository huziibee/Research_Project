"""AI-use log validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ambiguity_manager.governance.paths import is_absolute_machine_path, is_tracked_governance_log_path

AI_USE_LOG_SCHEMA_VERSION = "1.0.0"

AI_USE_CATEGORIES = frozenset(
    {
        "planning",
        "coding",
        "debugging",
        "data_authoring",
        "annotation_support",
        "model_inference",
        "analysis",
        "writing",
    }
)

TIME_PRECISIONS = frozenset({"exact", "period_only", "not_recorded"})
MODEL_STATUSES = frozenset({"not_recorded", "recorded"})


def load_ai_use_log(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        entries.append(json.loads(line))
    return entries


def validate_ai_use_entry(entry: dict[str, Any], *, line_number: int | None = None) -> list[str]:
    prefix = f"line {line_number}" if line_number is not None else "entry"
    errors: list[str] = []

    if not entry.get("entry_id"):
        errors.append(f"{prefix}: entry_id is required")

    categories = entry.get("use_categories")
    if not isinstance(categories, list) or not categories:
        errors.append(f"{prefix}: use_categories must be a non-empty list")
    else:
        if len(categories) != len(set(categories)):
            errors.append(f"{prefix}: use_categories must not contain duplicate values")
        unknown = [value for value in categories if value not in AI_USE_CATEGORIES]
        if unknown:
            errors.append(f"{prefix}: unknown use_categories: {unknown}")

    tools = entry.get("tools")
    if not isinstance(tools, list) or not tools:
        errors.append(f"{prefix}: tools must be a non-empty list")
    else:
        for index, tool in enumerate(tools):
            if not isinstance(tool, dict):
                errors.append(f"{prefix}: tools[{index}] must be an object")
                continue
            if not tool.get("provider"):
                errors.append(f"{prefix}: tools[{index}].provider is required")
            if tool.get("model_status") not in MODEL_STATUSES:
                errors.append(f"{prefix}: tools[{index}].model_status invalid")

    if entry.get("time_precision") not in TIME_PRECISIONS:
        errors.append(f"{prefix}: time_precision invalid")

    if not isinstance(entry.get("historical_backfill"), bool):
        errors.append(f"{prefix}: historical_backfill must be boolean")

    if entry.get("protected_data_involved") is True and not entry.get("authorization_ref"):
        errors.append(f"{prefix}: protected_data_involved requires authorization_ref")

    for rel_path in entry.get("related_files", []) or []:
        if isinstance(rel_path, str) and is_absolute_machine_path(rel_path):
            errors.append(f"{prefix}: related_files must be repository-relative")

    return errors


def validate_ai_use_log(entries: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for line_number, entry in enumerate(entries, start=1):
        entry_errors = validate_ai_use_entry(entry, line_number=line_number)
        errors.extend(entry_errors)
        entry_id = entry.get("entry_id")
        if isinstance(entry_id, str):
            if entry_id in seen_ids:
                errors.append(f"line {line_number}: duplicate entry_id {entry_id!r}")
            seen_ids.add(entry_id)
    return errors


def validate_ai_use_log_path(relative_path: str) -> list[str]:
    if not is_tracked_governance_log_path(relative_path):
        return [f"AI-use log must live under docs/governance/logs/: {relative_path!r}"]
    return []
