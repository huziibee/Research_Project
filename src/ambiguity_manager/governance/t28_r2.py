"""T28-R2A institutional internal academic research-use gate."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

APPROVAL_REL = "docs/licences/T28_internal_academic_research_use_approval.md"
R3_DECISION_REL = "docs/governance/decisions/T28-R3_internal_use_decision.json"
PRIMARY_DATASETS = ("ambik", "indirect_requests", "codraw_icr_v2", "vague", "clara")
ALL_COVERED_DATASETS = PRIMARY_DATASETS + ("clariq",)
DECISIONS = frozenset({"approved", "approved_with_conditions", "denied", "pending"})
REQUIRED_SCOPE = (
    "internal_noncommercial_training",
    "internal_development_checkpoint_selection",
    "aggregate_statistics_and_findings",
    "access_controlled_source_storage",
    "full_citation_and_attribution",
    "no_original_record_redistribution",
    "no_recoverable_transformed_text_redistribution",
    "no_commercial_use",
    "no_public_adapter_weights_until_release_review",
    "remove_or_suspend_on_rightsholder_objection",
    "ethics_popia_integrity_compliance",
)
APPROVAL_MARKER = re.compile(
    r"<!-- T28_R2A_APPROVAL_RECORD\s*\n(?P<payload>\{.*?\})\s*\n-->", re.DOTALL
)


def load_approval_document(repo_root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    path = repo_root / APPROVAL_REL
    if not path.is_file():
        return None, [f"missing {APPROVAL_REL}"]
    match = APPROVAL_MARKER.search(path.read_text(encoding="utf-8"))
    if not match:
        return None, ["approval document has no machine-readable T28_R2A record"]
    try:
        record = json.loads(match.group("payload"))
    except json.JSONDecodeError as exc:
        return None, [f"approval record JSON invalid: {exc.msg}"]
    return record, []


def approval_document_sha256(repo_root: Path) -> str:
    return hashlib.sha256((repo_root / APPROVAL_REL).read_bytes()).hexdigest()


def load_r3_decision(repo_root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    path = repo_root / R3_DECISION_REL
    if not path.is_file():
        return None, []
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"T28-R3 decision JSON invalid: {exc.msg}"]
    errors: list[str] = []
    if record.get("decision_type") != "human_internal_academic_use_authorisation":
        errors.append("T28-R3 decision type invalid")
    if record.get("decision_source") != "explicit human instruction in the T28-R3 launch prompt":
        errors.append("T28-R3 decision source invalid")
    if record.get("internal_training_gate") is not True:
        errors.append("T28-R3 internal training gate is not permitted")
    if record.get("dataset_licence_statuses_unchanged") is not True:
        errors.append("T28-R3 decision must preserve dataset licence statuses")
    for field in ("raw_data_redistribution_allowed", "transformed_text_redistribution_allowed", "commercial_use_allowed", "adapter_public_release_allowed", "public_release_allowed"):
        if record.get(field) is not False:
            errors.append(f"T28-R3 {field} must remain false")
    if record.get("institutional_signature_or_author_permission") is not None:
        errors.append("T28-R3 must not fabricate institutional or author permission")
    return record, errors


def validate_approval_record(record: dict[str, Any], *, repo_root: Path) -> list[str]:
    errors: list[str] = []
    if record.get("approval_status") not in DECISIONS:
        errors.append("approval_status invalid")
    if record.get("internal_academic_research_use") not in DECISIONS:
        errors.append("internal_academic_research_use invalid")
    if record.get("datasets_covered") != list(ALL_COVERED_DATASETS):
        errors.append("approval must list the five primary datasets and auxiliary-only ClariQ")
    if not isinstance(record.get("scope"), list) or not set(REQUIRED_SCOPE).issubset(record["scope"]):
        errors.append("approval scope does not contain all required conditions")
    if record.get("student_name") == record.get("approving_authority"):
        errors.append("student cannot be the approving authority")
    if record.get("approval_status") in {"approved", "approved_with_conditions"}:
        if not record.get("approval_date") or not record.get("signature_or_recorded_written_approval"):
            errors.append("approved gate requires approval date and recorded written approval")
        if record.get("approving_authority_role") == "student" or record.get("student_name") == record.get("approving_authority"):
            errors.append("student self-approval is not valid")
    if record.get("raw_data_redistribution") is not False:
        errors.append("raw_data_redistribution must remain false")
    if record.get("adapter_release_permission") not in {False, "pending"}:
        errors.append("adapter release permission must remain false or pending")
    if record.get("does_not_declare_open_licence") is not True:
        errors.append("approval must not declare datasets openly licensed")
    if record.get("does_not_authorise_public_redistribution") is not True:
        errors.append("approval must not authorise public redistribution")
    if record.get("approval_status") in {"approved", "approved_with_conditions"}:
        if record.get("approving_authority_role") == "student":
            errors.append("student self-approval rejected")
    return errors


def validate_internal_research_gate(register: dict[str, Any], *, repo_root: Path) -> list[str]:
    errors: list[str] = []
    r3_record, r3_errors = load_r3_decision(repo_root)
    if r3_record is not None:
        errors.extend(r3_errors)
        gate = register.get("internal_academic_research_use_gate")
        if not isinstance(gate, dict):
            return errors + ["missing internal_academic_research_use_gate"]
        if gate.get("decision") != "approved_with_conditions":
            errors.append("register gate must be approved_with_conditions under T28-R3")
        if gate.get("decision_record") != R3_DECISION_REL:
            errors.append("register gate decision_record mismatch")
        entries = {entry.get("dataset_id"): entry for entry in register.get("entries", [])}
        for dataset_id in ALL_COVERED_DATASETS:
            if entries.get(dataset_id, {}).get("internal_academic_research_use") != gate.get("decision"):
                errors.append(f"{dataset_id}: internal_academic_research_use does not match gate")
        return errors
    record, load_errors = load_approval_document(repo_root)
    errors.extend(load_errors)
    gate = register.get("internal_academic_research_use_gate")
    if not isinstance(gate, dict):
        errors.append("missing internal_academic_research_use_gate")
        return errors
    if gate.get("decision") not in DECISIONS:
        errors.append("gate decision invalid")
    if record is not None:
        errors.extend(validate_approval_record(record, repo_root=repo_root))
        if gate.get("decision") != record.get("internal_academic_research_use"):
            errors.append("register gate decision does not match approval record")
        expected_hash = approval_document_sha256(repo_root)
        if gate.get("approval_document_sha256") != expected_hash:
            errors.append("approval document hash mismatch")
    entries = {entry.get("dataset_id"): entry for entry in register.get("entries", [])}
    for dataset_id in ALL_COVERED_DATASETS:
        if entries.get(dataset_id, {}).get("internal_academic_research_use") != gate.get("decision"):
            errors.append(f"{dataset_id}: internal_academic_research_use does not match gate")
    return errors


def training_allowed(register: dict[str, Any], *, repo_root: Path) -> tuple[bool, list[str]]:
    errors = validate_internal_research_gate(register, repo_root=repo_root)
    gate = register.get("internal_academic_research_use_gate", {})
    if gate.get("decision") not in {"approved", "approved_with_conditions"}:
        errors.append("internal academic research-use approval is not active")
    entries = {entry.get("dataset_id"): entry for entry in register.get("entries", [])}
    for dataset_id in PRIMARY_DATASETS:
        entry = entries.get(dataset_id, {})
        if entry.get("explicit_prohibition_against_internal_training") is True:
            errors.append(f"{dataset_id}: explicit source prohibition overrides institutional approval")
        if entry.get("attribution_required") is not True:
            errors.append(f"{dataset_id}: attribution requirement not recorded")
    if gate.get("raw_data_redistribution") is not False:
        errors.append("raw data redistribution is not prohibited")
    if gate.get("adapter_release_permission") not in {False, "pending"}:
        errors.append("adapter release is not blocked")
    return not errors, errors
