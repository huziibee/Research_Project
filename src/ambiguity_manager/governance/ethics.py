"""Human-annotation ethics determination validation."""

from __future__ import annotations

from typing import Any

ETHICS_SCHEMA_VERSION = "1.0.0"

DETERMINATION_STATUSES = frozenset(
    {
        "pending",
        "approved",
        "exempt_confirmed",
        "approval_required",
        "rejected",
        "blocked",
    }
)


def derive_collection_permitted(record: dict[str, Any]) -> bool:
    status = record.get("determination_status")
    if status in {"approved", "exempt_confirmed"}:
        return True
    return False


def derive_ticket_verdict(record: dict[str, Any]) -> str:
    status = record.get("determination_status")
    if status == "pending":
        return "BLOCKED"
    if status in {"approved", "exempt_confirmed", "approval_required"}:
        return "PASS"
    if status == "rejected":
        return "FAIL"
    if status == "blocked":
        return "BLOCKED"
    return "BLOCKED"


def validate_ethics_determination(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if record.get("governance_schema_version") != ETHICS_SCHEMA_VERSION:
        errors.append(f"governance_schema_version must be {ETHICS_SCHEMA_VERSION}")

    status = record.get("determination_status")
    if status not in DETERMINATION_STATUSES:
        errors.append("determination_status invalid")

    expected_collection = derive_collection_permitted(record)
    if record.get("collection_permitted") is not expected_collection:
        errors.append("collection_permitted must match determination_status gate semantics")

    if status == "approval_required" and not record.get("determination_status_evidence"):
        errors.append("approval_required requires determination_status_evidence")

    if status in {"approved", "exempt_confirmed"} and not record.get("determination_status_evidence"):
        errors.append(f"{status} requires determination_status_evidence")

    for field_name in (
        "compensation_policy",
        "retention_period",
        "deletion_policy",
        "informed_consent_required",
        "personal_data_collected",
        "responsible_authority",
        "institution",
        "identity_mapping_store",
    ):
        field = record.get(field_name)
        if isinstance(field, dict) and field.get("status") == "pending_human_confirmation":
            if field.get("value") not in (None, []):
                errors.append(f"{field_name}.value must be null while status is pending_human_confirmation")

    pseudonyms = record.get("role_pseudonyms", {})
    expected = {
        "annotator_a": "ANN-A",
        "annotator_b": "ANN-B",
        "adjudicator": "ADJ-01",
        "author": "AUTHOR-01",
    }
    for key, value in expected.items():
        if pseudonyms.get(key) != value:
            errors.append(f"role_pseudonyms.{key} must be {value!r}")

    return errors
