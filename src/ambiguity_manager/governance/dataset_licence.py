"""Dataset licence register validation."""

from __future__ import annotations

from typing import Any

T02_HISTORICAL_MANIFEST_REL = "configs/datasets/licence_provenance_manifest.json"
REGISTER_SCHEMA_VERSION = "2.0.0"

SUPPORTED_SPDX_IDENTIFIERS = frozenset(
    {
        "Apache-2.0",
        "MIT",
        "CC-BY-4.0",
        "CC-BY-SA-4.0",
        "CC-BY-NC-4.0",
        "CC-BY-NC-SA-4.0",
        "CC0-1.0",
    }
)

VERIFICATION_STATUSES = frozenset(
    {
        "verified",
        "unresolved",
        "stated_unverified",
        "not_yet_acquired",
        "excluded",
    }
)

PERMISSION_FIELDS = (
    "local_storage_permitted",
    "conversion_permitted",
    "training_permitted",
    "evaluation_permitted",
    "redistribution_permitted",
    "public_release_permitted",
)


def permission_allows(value: bool | None) -> bool:
    return value is True


def _has_evidence(entry: dict[str, Any]) -> bool:
    return bool(
        entry.get("evidence_path")
        or entry.get("institutional_decision_ref")
        or entry.get("licence_file_relpath")
        or entry.get("licence_url")
    )


def validate_dataset_licence_entry(entry: dict[str, Any], *, index: int) -> list[str]:
    prefix = f"entries[{index}]"
    errors: list[str] = []

    if entry.get("verification_status") not in VERIFICATION_STATUSES:
        errors.append(f"{prefix}.verification_status invalid")

    if entry.get("verification_status") == "verified" and not _has_evidence(entry):
        errors.append(f"{prefix}.verified requires evidence_path or institutional_decision_ref")

    dataset_identifier = entry.get("dataset_licence_identifier")
    if dataset_identifier is not None and dataset_identifier not in SUPPORTED_SPDX_IDENTIFIERS:
        if entry.get("dataset_licence_kind") != "custom_terms":
            errors.append(f"{prefix}.dataset_licence_identifier is not a supported SPDX identifier")

    evidence_url_or_path = entry.get("evidence_url_or_path")
    evidence_hash = entry.get("evidence_hash")
    if evidence_url_or_path and (not isinstance(evidence_hash, str) or len(evidence_hash) != 64):
        errors.append(f"{prefix}.evidence_hash is required for every evidence artifact")
    if evidence_hash is not None and (
        not isinstance(evidence_hash, str) or len(evidence_hash) != 64 or any(c not in "0123456789abcdef" for c in evidence_hash.lower())
    ):
        errors.append(f"{prefix}.evidence_hash must be a lowercase SHA-256")
    if entry.get("evidence_type") == "public_repository_only" and entry.get("verification_status") == "verified":
        errors.append(f"{prefix}.public repository alone cannot verify a dataset")
    if entry.get("verification_status") == "verified" and entry.get("dependency_status") == "unresolved":
        errors.append(f"{prefix}.dependency_status unresolved blocks verification")
    if entry.get("verification_status") == "verified" and entry.get("dataset_licence_status") != "verified":
        errors.append(f"{prefix}.verified requires dataset_licence_status verified")

    for field_name in PERMISSION_FIELDS:
        value = entry.get(field_name)
        if value is not None and not isinstance(value, bool):
            errors.append(f"{prefix}.{field_name} must be true, false, or null")

    status = entry.get("verification_status")
    if status in {"unresolved", "stated_unverified"}:
        for field_name in ("training_permitted", "evaluation_permitted", "redistribution_permitted"):
            if permission_allows(entry.get(field_name)):
                errors.append(
                    f"{prefix}.{field_name} cannot be true while verification_status is {status!r}"
                )

    return errors


def validate_dataset_licence_register(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if data.get("register_schema_version") != REGISTER_SCHEMA_VERSION:
        errors.append(f"register_schema_version must be {REGISTER_SCHEMA_VERSION}")

    if data.get("historical_evidence_manifest") != T02_HISTORICAL_MANIFEST_REL:
        errors.append("historical_evidence_manifest must reference T02 manifest")

    if data.get("authoritative") is not True:
        errors.append("authoritative must be true")

    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("entries must be a non-empty list")
        return errors

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entries[{index}] must be an object")
            continue
        errors.extend(validate_dataset_licence_entry(entry, index=index))

    return errors
