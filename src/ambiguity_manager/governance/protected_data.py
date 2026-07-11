"""Protected-data policy validation."""

from __future__ import annotations

from typing import Any

POLICY_SCHEMA_VERSION = "1.0.0"


def validate_protected_data_policy(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if data.get("policy_schema_version") != POLICY_SCHEMA_VERSION:
        errors.append(f"policy_schema_version must be {POLICY_SCHEMA_VERSION}")

    lifecycle = data.get("lifecycle", {})
    if lifecycle.get("t15_construction_access_permitted") is not True:
        errors.append("lifecycle.t15_construction_access_permitted must be true")
    if lifecycle.get("post_t15_seal_prohibited_uses") is None:
        errors.append("lifecycle.post_t15_seal_prohibited_uses is required")

    return errors
