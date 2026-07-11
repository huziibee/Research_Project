"""Model licence register validation."""

from __future__ import annotations

from typing import Any

REGISTER_SCHEMA_VERSION = "1.0.0"


def validate_model_licence_register(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if data.get("register_schema_version") != REGISTER_SCHEMA_VERSION:
        errors.append(f"register_schema_version must be {REGISTER_SCHEMA_VERSION}")

    if data.get("selected_model") is not None:
        errors.append("selected_model must be null before T12")

    entries = data.get("entries")
    if entries is None:
        errors.append("entries is required")
    elif not isinstance(entries, list):
        errors.append("entries must be a list")

    return errors
