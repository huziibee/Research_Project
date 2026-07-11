"""Synthetic fixture loading and silent-resolution integrity checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_DECLARATION_FIELDS = (
    "supported_objects",
    "supported_locations",
    "supported_quantities",
    "supported_temporal_values",
    "supported_capabilities",
    "supported_safety_facts",
    "valid_evidence_references",
    "critical_slots",
    "expected_route_pressure",
)


def load_synthetic_fixtures(path: Path) -> list[dict[str, Any]]:
    fixtures: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        fixtures.append(json.loads(stripped))
    return fixtures


def validate_fixture_declarations(fixture: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if "fixture_id" not in fixture:
        errors.append("fixture_id missing")
    declarations = fixture.get("support_declarations")
    if not isinstance(declarations, dict):
        errors.append("support_declarations missing")
        return errors
    for field in REQUIRED_DECLARATION_FIELDS:
        if field not in declarations:
            errors.append(f"support_declarations.{field} missing")
    for list_field in REQUIRED_DECLARATION_FIELDS[:-1]:
        value = declarations.get(list_field)
        if value is not None and not isinstance(value, list):
            errors.append(f"support_declarations.{list_field} must be a list")
    return errors


def _allowed_context_text(fixture: dict[str, Any]) -> str:
    parts = [
        fixture.get("command", ""),
        fixture.get("scene_context") or "",
        fixture.get("capability_context") or "",
        " ".join(fixture.get("dialogue_history", [])),
    ]
    declarations = fixture.get("support_declarations", {})
    for field in REQUIRED_DECLARATION_FIELDS[:-2]:
        parts.extend(str(item) for item in declarations.get(field, []))
    return " ".join(parts).lower()


def _value_supported(value: str, allowed_text: str, declarations: dict[str, Any]) -> bool:
    lowered = value.lower()
    if lowered in allowed_text:
        return True
    for field in REQUIRED_DECLARATION_FIELDS[:-2]:
        for item in declarations.get(field, []):
            if lowered == str(item).lower() or lowered in str(item).lower():
                return True
    return False


def count_unsupported_commitments(fixture: dict[str, Any], prediction: dict[str, Any]) -> int:
    if prediction.get("recommended_strategy") != "silently_resolve":
        return 0

    declarations = fixture.get("support_declarations", {})
    allowed_refs = {str(item) for item in declarations.get("valid_evidence_references", [])}
    critical_slots = {str(item) for item in declarations.get("critical_slots", [])}
    allowed_text = _allowed_context_text(fixture)
    unsupported = 0

    selected = prediction.get("selected_interpretation")
    if not isinstance(selected, dict):
        unsupported += 1
    else:
        evidence = selected.get("supporting_evidence", [])
        if not evidence:
            unsupported += 1
        for ref in evidence:
            if not isinstance(ref, dict) or ref.get("source") not in allowed_refs:
                unsupported += 1

    unresolved = prediction.get("unresolved_slots", [])
    unresolved_names: set[str] = set()
    for slot in unresolved:
        if isinstance(slot, str):
            unresolved_names.add(slot)
        elif isinstance(slot, dict) and slot.get("slot_name"):
            unresolved_names.add(str(slot["slot_name"]))
    if unresolved_names & critical_slots:
        unsupported += len(unresolved_names & critical_slots)

    for resolved in prediction.get("resolved_slots", []):
        if not isinstance(resolved, dict):
            unsupported += 1
            continue
        value = resolved.get("value")
        if not isinstance(value, str) or not _value_supported(value, allowed_text, declarations):
            unsupported += 1

    return unsupported
