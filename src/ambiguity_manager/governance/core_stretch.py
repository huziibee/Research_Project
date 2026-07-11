"""Core versus stretch policy validation."""

from __future__ import annotations

from typing import Any

from ambiguity_manager.governance.research_contract import MANDATORY_SYSTEM_IDS

POLICY_SCHEMA_VERSION = "1.0.0"

MANDATORY_CORE_TICKETS = [
    "T10", "T11", "T12", "T13", "T14", "T15", "T16", "T17", "T18", "T19",
    "T20", "T21", "T22", "T23", "T24", "T26", "T27", "T28", "T29", "T30",
    "T31", "T32", "T33", "T36", "T37", "T38",
]

STRETCH_TICKETS = ["T25", "T34", "T35"]


def validate_core_stretch_policy(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if data.get("policy_schema_version") != POLICY_SCHEMA_VERSION:
        errors.append(f"policy_schema_version must be {POLICY_SCHEMA_VERSION}")

    if data.get("mandatory_core_tickets") != MANDATORY_CORE_TICKETS:
        errors.append("mandatory_core_tickets must match canonical core ticket list")

    if data.get("stretch_nonblocking_tickets") != STRETCH_TICKETS:
        errors.append("stretch_nonblocking_tickets must match canonical stretch ticket list")

    if data.get("seven_systems_mandatory") is not True:
        errors.append("seven_systems_mandatory must be true")

    if data.get("mandatory_system_ids") != MANDATORY_SYSTEM_IDS:
        errors.append("mandatory_system_ids must match canonical seven-system list")

    if data.get("mandatory_finetuning") is not True:
        errors.append("mandatory_finetuning must be true")

    overrides = data.get("ticket_status_overrides", {})
    if isinstance(overrides, dict):
        for ticket_id, status in overrides.items():
            if ticket_id in MANDATORY_CORE_TICKETS and status == "BLOCKED_NONCRITICAL":
                errors.append(f"core ticket {ticket_id} cannot use BLOCKED_NONCRITICAL")

    return errors
