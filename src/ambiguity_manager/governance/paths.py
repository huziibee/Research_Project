"""Governance path helpers."""

from __future__ import annotations

TRACKED_GOVERNANCE_LOG_PREFIX = "docs/governance/logs/"


def is_tracked_governance_log_path(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    return normalized.startswith(TRACKED_GOVERNANCE_LOG_PREFIX) and normalized.endswith(".jsonl")


def is_absolute_machine_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    if "://" in normalized:
        return True
    if len(normalized) >= 2 and normalized[1] == ":":
        return True
    return normalized.startswith("/home/") or normalized.startswith("/Users/")
