"""Human-annotation ethics determination validation."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ETHICS_SCHEMA_VERSION = "1.0.0"

DETERMINATION_STATUSES = frozenset(
    {
        "pending",
        "not_required",
        "approved",
        "exempt_confirmed",
        "approval_required",
        "rejected",
        "blocked",
    }
)

SUPERVISOR_ONLY_BASIS = "supervisor_only_annotation"
SUPERVISOR_ONLY_SCOPE = "project_supervisors_only"
EVIDENCE_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

REQUIRED_NOT_REQUIRED_FIELDS = (
    "determination_basis",
    "ethics_clearance_required",
    "ethics_waiver_required",
    "annotator_scope",
    "external_annotators_permitted",
    "reassessment_required_if_scope_changes",
    "collection_permitted",
    "determination_status_evidence",
    "determination_evidence",
    "external_annotator_recruitment",
    "external_participant_recruitment",
    "incentives_offered",
    "external_consent_workflow",
)

REQUIRED_EVIDENCE_FIELDS = (
    "evidence_id",
    "evidence_path",
    "evidence_date",
    "evidence_type",
)

_BOOL_FIELDS_NOT_REQUIRED = (
    "ethics_clearance_required",
    "ethics_waiver_required",
    "external_annotators_permitted",
    "reassessment_required_if_scope_changes",
    "collection_permitted",
    "external_annotator_recruitment",
    "external_participant_recruitment",
    "incentives_offered",
    "external_consent_workflow",
)


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def supervisor_only_invariants_hold(record: dict[str, Any]) -> bool:
    """Return True when supervisor-only not_required machine invariants hold (no I/O)."""
    return (
        record.get("determination_status") == "not_required"
        and record.get("determination_basis") == SUPERVISOR_ONLY_BASIS
        and record.get("ethics_clearance_required") is False
        and record.get("ethics_waiver_required") is False
        and record.get("annotator_scope") == SUPERVISOR_ONLY_SCOPE
        and record.get("external_annotators_permitted") is False
        and record.get("reassessment_required_if_scope_changes") is True
        and record.get("external_annotator_recruitment") is False
        and record.get("external_participant_recruitment") is False
        and record.get("incentives_offered") is False
        and record.get("external_consent_workflow") is False
        and bool(record.get("determination_status_evidence"))
    )


def derive_collection_permitted(record: dict[str, Any]) -> bool:
    status = record.get("determination_status")
    if status in {"approved", "exempt_confirmed"}:
        return True
    if status == "not_required":
        return supervisor_only_invariants_hold(record)
    return False


def derive_ticket_verdict(record: dict[str, Any]) -> str:
    status = record.get("determination_status")
    if status == "pending":
        return "BLOCKED"
    if status == "not_required":
        return "PASS"
    if status in {"approved", "exempt_confirmed", "approval_required"}:
        return "PASS"
    if status == "rejected":
        return "FAIL"
    if status == "blocked":
        return "BLOCKED"
    return "BLOCKED"


def _validate_boolean_fields(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field_name in _BOOL_FIELDS_NOT_REQUIRED:
        if field_name not in record:
            continue
        if not _is_bool(record.get(field_name)):
            errors.append(
                f"{field_name} must be a Boolean, not {type(record.get(field_name)).__name__}"
            )
    return errors


def _validate_not_required_evidence(
    record: dict[str, Any],
    *,
    repo_root: Path | None,
) -> list[str]:
    errors: list[str] = []
    evidence_ref = record.get("determination_status_evidence")
    if not isinstance(evidence_ref, str) or not evidence_ref.strip():
        errors.append("not_required requires determination_status_evidence")

    evidence = record.get("determination_evidence")
    if not isinstance(evidence, dict):
        errors.append("not_required requires determination_evidence object")
        return errors

    for field_name in REQUIRED_EVIDENCE_FIELDS:
        if field_name not in evidence:
            errors.append(f"determination_evidence.{field_name} is required")

    if evidence.get("evidence_id") != "ETHGOV-001":
        errors.append("determination_evidence.evidence_id must be 'ETHGOV-001'")

    evidence_path = evidence.get("evidence_path")
    if not isinstance(evidence_path, str) or not evidence_path.strip():
        errors.append("determination_evidence.evidence_path is required")
    elif isinstance(evidence_ref, str) and evidence_ref != evidence_path:
        errors.append(
            "determination_status_evidence must match determination_evidence.evidence_path"
        )

    evidence_date = evidence.get("evidence_date")
    if not isinstance(evidence_date, str) or not EVIDENCE_DATE_RE.fullmatch(evidence_date):
        errors.append("determination_evidence.evidence_date must match YYYY-MM-DD")
    else:
        try:
            datetime.strptime(evidence_date, "%Y-%m-%d")
        except ValueError:
            errors.append("determination_evidence.evidence_date is not a valid calendar date")

    if evidence.get("evidence_type") != "institutional_email_guidance":
        errors.append(
            "determination_evidence.evidence_type must be 'institutional_email_guidance'"
        )

    digest = evidence.get("evidence_sha256")
    if digest is not None and (
        not isinstance(digest, str) or not SHA256_RE.fullmatch(digest)
    ):
        errors.append("determination_evidence.evidence_sha256 must be 64-char lowercase hex")

    if repo_root is not None and isinstance(evidence_path, str) and evidence_path.strip():
        evidence_file = repo_root / evidence_path
        if not evidence_file.is_file():
            errors.append(f"determination evidence path does not exist: {evidence_path!r}")
        elif isinstance(digest, str) and SHA256_RE.fullmatch(digest):
            actual = hashlib.sha256(evidence_file.read_bytes()).hexdigest()
            if actual != digest:
                errors.append(
                    "determination_evidence.evidence_sha256 does not match evidence file"
                )

    return errors


def _validate_annotators(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    annotators = record.get("annotators")
    if not isinstance(annotators, list) or len(annotators) != 2:
        errors.append("not_required requires exactly two project-supervisor annotators")
        return errors

    expected_names = {"Steven James", "Benjamin Rosman"}
    seen_names: set[str] = set()
    for index, annotator in enumerate(annotators):
        if not isinstance(annotator, dict):
            errors.append(f"annotators[{index}] must be an object")
            continue
        name = annotator.get("name")
        role = annotator.get("role")
        if not isinstance(name, str) or name not in expected_names:
            errors.append(f"annotators[{index}].name must be one of the project supervisors")
        else:
            if name in seen_names:
                errors.append("annotators must not duplicate supervisor names")
            seen_names.add(name)
        if role != "project_supervisor":
            errors.append(f"annotators[{index}].role must be 'project_supervisor'")
        for forbidden in ("email", "phone", "address", "contact"):
            if forbidden in annotator:
                errors.append(f"annotators[{index}] must not include {forbidden}")
    if seen_names != expected_names:
        errors.append("annotators must name both Steven James and Benjamin Rosman")
    return errors


def _validate_not_required(
    record: dict[str, Any],
    *,
    repo_root: Path | None,
) -> list[str]:
    errors: list[str] = []

    for field_name in REQUIRED_NOT_REQUIRED_FIELDS:
        if field_name not in record:
            errors.append(f"not_required requires field {field_name!r}")

    errors.extend(_validate_boolean_fields(record))

    if record.get("determination_basis") != SUPERVISOR_ONLY_BASIS:
        errors.append(
            "not_required determination_basis must be " f"{SUPERVISOR_ONLY_BASIS!r}"
        )

    for field_name, expected in (
        ("ethics_clearance_required", False),
        ("ethics_waiver_required", False),
        ("reassessment_required_if_scope_changes", True),
        ("external_participant_recruitment", False),
        ("incentives_offered", False),
        ("external_consent_workflow", False),
    ):
        value = record.get(field_name)
        if _is_bool(value) and value is not expected:
            errors.append(
                f"{field_name} must be {expected} for not_required supervisor-only scope"
            )

    drifted = False
    if record.get("external_annotators_permitted") is True:
        drifted = True
        errors.append(
            "external annotators are not permitted under not_required; "
            "set collection_permitted false and obtain a fresh determination"
        )
    if record.get("external_annotator_recruitment") is True:
        drifted = True
        errors.append(
            "scope drift: external_annotator_recruitment requires reassessment before collection"
        )
    if record.get("annotator_scope") != SUPERVISOR_ONLY_SCOPE:
        drifted = True
        errors.append(
            "annotator_scope must be "
            f"{SUPERVISOR_ONLY_SCOPE!r} for not_required determination"
        )

    if drifted:
        if record.get("collection_permitted") is not False:
            errors.append(
                "scope drift: collection_permitted must be false when leaving "
                "supervisor-only scope"
            )
    else:
        if record.get("external_annotators_permitted") is not False and _is_bool(
            record.get("external_annotators_permitted")
        ):
            errors.append("external_annotators_permitted must be false")
        if record.get("external_annotator_recruitment") is not False and _is_bool(
            record.get("external_annotator_recruitment")
        ):
            errors.append("external_annotator_recruitment must be false")
        if _is_bool(record.get("collection_permitted")) and record.get(
            "collection_permitted"
        ) is not True:
            errors.append(
                "collection_permitted must be true for valid not_required "
                "supervisor-only scope"
            )

    errors.extend(_validate_not_required_evidence(record, repo_root=repo_root))
    errors.extend(_validate_annotators(record))
    return errors


def validate_scope_change_guard(record: dict[str, Any]) -> list[str]:
    """Public alias for drift checks used by tests; delegates to not_required validation."""
    if record.get("determination_status") != "not_required":
        return []
    return _validate_not_required(record, repo_root=None)


def validate_ethics_determination(
    record: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> list[str]:
    errors: list[str] = []

    if record.get("governance_schema_version") != ETHICS_SCHEMA_VERSION:
        errors.append(f"governance_schema_version must be {ETHICS_SCHEMA_VERSION}")

    status = record.get("determination_status")
    if status not in DETERMINATION_STATUSES:
        errors.append("determination_status invalid")

    if status == "approval_required" and not record.get("determination_status_evidence"):
        errors.append("approval_required requires determination_status_evidence")

    if status in {"approved", "exempt_confirmed"} and not record.get(
        "determination_status_evidence"
    ):
        errors.append(f"{status} requires determination_status_evidence")

    if status == "not_required":
        errors.extend(_validate_not_required(record, repo_root=repo_root))
    else:
        expected_collection = derive_collection_permitted(record)
        if record.get("collection_permitted") is not expected_collection:
            errors.append("collection_permitted must match determination_status gate semantics")

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
                errors.append(
                    f"{field_name}.value must be null while status is "
                    "pending_human_confirmation"
                )

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
