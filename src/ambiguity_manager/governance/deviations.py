"""Deviation log validation."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ambiguity_manager.governance.paths import is_repository_relative_path, is_tracked_governance_log_path

DEVIATION_RECORD_SCHEMA_VERSION = "1.0.0"

DEVIATION_ID_RE = re.compile(r"^DEV-[0-9]{8}-[0-9]{3}$")
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
TICKET_ID_RE = re.compile(r"^T(0[0-9]|[12][0-9]|3[0-8])$")

DEVIATION_STATUSES = frozenset({"proposed", "accepted", "rejected"})
CHANGE_TYPES = frozenset(
    {
        "execution_order_exception",
        "protocol_amendment",
        "licence_exception",
        "metric_exception",
        "schedule_exception",
        "deviation_closure",
    }
)

REQUIRED_FIELDS = (
    "deviation_id",
    "date",
    "status",
    "change_type",
    "approver",
    "approval_basis",
    "protocol_version_before",
    "protocol_version_after",
    "affected_tickets",
    "affected_artefacts",
    "summary",
    "rationale",
    "evidence",
    "risk",
    "required_reruns",
    "protected_test_implications",
    "preservation_of_prior_outputs",
    "ethics_disclaimer",
)

ETHICS_BYPASS_PATTERNS = (
    re.compile(r"\bcollection_permitted\s*:\s*true\b", re.IGNORECASE),
    re.compile(r"\bcollection_permitted\s*=\s*true\b", re.IGNORECASE),
    re.compile(r"\bT11\b[^\n]{0,40}\bPASS\b", re.IGNORECASE),
    re.compile(r"\bdetermination_status\s*:\s*[\"']approved[\"']", re.IGNORECASE),
    re.compile(r"\bt11_verdict_override\b", re.IGNORECASE),
)

T12_SCOPE_REQUIRED_PHRASES = (
    "rtx 3070",
    "synthetic",
    "non-protected",
    "licence",
    "adapter-load",
)

T12_SCOPE_PROHIBITED_PHRASES = (
    "protected data",
    "collect annotations",
    "fine-tune on research",
    "begin t13",
    "begin t14",
)

CLOSURE_REQUIRED_PHRASES = (
    "ethgov-001",
    "dev-20260711-001",
    "not_required",
    "completed work",
    "external",
)


def load_deviation_log(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    if not path.is_file():
        return [], []
    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: malformed JSON: {exc.msg}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"line {line_number}: entry must be a JSON object")
            continue
        entries.append(payload)
    return entries, errors


def _protocol_unchanged(before: str, after: str) -> bool:
    if before.strip() == after.strip():
        return True
    return after.strip().lower().startswith("unchanged")


def _combined_text(entry: dict[str, Any]) -> str:
    parts = [
        entry.get("summary", ""),
        entry.get("rationale", ""),
        entry.get("preservation_of_prior_outputs", ""),
        entry.get("ethics_disclaimer", ""),
    ]
    return "\n".join(str(part) for part in parts if part)


def _validate_repository_path_field(
    value: str,
    *,
    prefix: str,
    repo_root: Path | None,
    require_exists: bool,
) -> list[str]:
    errors: list[str] = []
    if not is_repository_relative_path(value):
        errors.append(f"{prefix}: must be a repository-relative path")
        return errors
    if require_exists and repo_root is not None and not (repo_root / value).is_file():
        errors.append(f"{prefix}: referenced path does not exist: {value!r}")
    return errors


def _validate_deviation_closure(
    entry: dict[str, Any],
    *,
    prefix: str,
    combined: str,
) -> list[str]:
    errors: list[str] = []
    closes = entry.get("closes_deviation_id")
    if closes != "DEV-20260711-001":
        errors.append(f"{prefix}: deviation_closure must set closes_deviation_id to DEV-20260711-001")

    closure_basis = entry.get("closure_basis")
    if not isinstance(closure_basis, str) or "ETHGOV-001" not in closure_basis:
        errors.append(f"{prefix}: deviation_closure must set closure_basis referencing ETHGOV-001")

    combined_lower = combined.lower()
    for phrase in CLOSURE_REQUIRED_PHRASES:
        if phrase not in combined_lower:
            errors.append(f"{prefix}: deviation_closure text must document {phrase!r}")

    ethics_disclaimer = entry.get("ethics_disclaimer", "")
    if isinstance(ethics_disclaimer, str):
        disclaimer_lower = ethics_disclaimer.lower()
        if "institutional ethics determination remains pending" in disclaimer_lower:
            errors.append(
                f"{prefix}: closure ethics_disclaimer must not claim the determination remains pending"
            )
        if "does not constitute or imply institutional ethics approval" not in disclaimer_lower:
            errors.append(
                f"{prefix}: ethics_disclaimer must state this is not institutional ethics approval"
            )
        if "not_required" not in disclaimer_lower:
            errors.append(
                f"{prefix}: closure ethics_disclaimer must record determination status not_required"
            )

    return errors


def validate_deviation_entry(
    entry: dict[str, Any],
    *,
    line_number: int | None = None,
    repo_root: Path | None = None,
) -> list[str]:
    prefix = f"line {line_number}" if line_number is not None else "entry"
    errors: list[str] = []

    for field_name in REQUIRED_FIELDS:
        if field_name not in entry:
            errors.append(f"{prefix}: missing required field {field_name!r}")

    deviation_id = entry.get("deviation_id")
    if not isinstance(deviation_id, str) or not DEVIATION_ID_RE.fullmatch(deviation_id):
        errors.append(f"{prefix}: deviation_id must match DEV-YYYYMMDD-NNN")

    date_value = entry.get("date")
    if not isinstance(date_value, str) or not DATE_RE.fullmatch(date_value):
        errors.append(f"{prefix}: date must match YYYY-MM-DD")
    elif isinstance(date_value, str) and DATE_RE.fullmatch(date_value):
        try:
            datetime.strptime(date_value, "%Y-%m-%d")
        except ValueError:
            errors.append(f"{prefix}: date is not a valid calendar date")

    status = entry.get("status")
    if status not in DEVIATION_STATUSES:
        errors.append(f"{prefix}: status must be one of proposed, accepted, rejected")

    change_type = entry.get("change_type")
    if change_type not in CHANGE_TYPES:
        errors.append(f"{prefix}: change_type invalid")

    approver = entry.get("approver")
    approval_basis = entry.get("approval_basis")
    if status == "accepted":
        if not isinstance(approver, str) or not approver.strip():
            errors.append(f"{prefix}: accepted entries require a non-empty approver")
        if not isinstance(approval_basis, str) or not approval_basis.strip():
            errors.append(f"{prefix}: accepted entries require a non-empty approval_basis")

    for field_name in ("protocol_version_before", "protocol_version_after"):
        value = entry.get(field_name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{prefix}: {field_name} must be explicit and non-empty")

    before = entry.get("protocol_version_before")
    after = entry.get("protocol_version_after")
    if isinstance(before, str) and isinstance(after, str):
        if (
            _protocol_unchanged(before, after)
            and change_type not in {"execution_order_exception", "deviation_closure"}
        ):
            errors.append(
                f"{prefix}: unchanged protocol_version_after requires "
                "change_type execution_order_exception or deviation_closure"
            )

    affected_tickets = entry.get("affected_tickets")
    if not isinstance(affected_tickets, list) or not affected_tickets:
        errors.append(f"{prefix}: affected_tickets must be a non-empty list")
    else:
        if len(affected_tickets) != len(set(affected_tickets)):
            errors.append(f"{prefix}: affected_tickets must not contain duplicates")
        for index, ticket_id in enumerate(affected_tickets):
            if not isinstance(ticket_id, str) or not TICKET_ID_RE.fullmatch(ticket_id):
                errors.append(f"{prefix}: affected_tickets[{index}] invalid ticket identifier")

    affected_artefacts = entry.get("affected_artefacts")
    if not isinstance(affected_artefacts, list) or not affected_artefacts:
        errors.append(f"{prefix}: affected_artefacts must be a non-empty list")
    else:
        for index, rel_path in enumerate(affected_artefacts):
            if not isinstance(rel_path, str):
                errors.append(f"{prefix}: affected_artefacts[{index}] must be a string")
                continue
            errors.extend(
                _validate_repository_path_field(
                    rel_path,
                    prefix=f"{prefix}: affected_artefacts[{index}]",
                    repo_root=repo_root,
                    require_exists=True,
                )
            )

    for text_field in (
        "summary",
        "rationale",
        "risk",
        "required_reruns",
        "protected_test_implications",
        "preservation_of_prior_outputs",
        "ethics_disclaimer",
    ):
        value = entry.get(text_field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{prefix}: {text_field} must be a non-empty string")

    evidence = entry.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append(f"{prefix}: evidence must be a non-empty list")
    else:
        for index, rel_path in enumerate(evidence):
            if not isinstance(rel_path, str):
                errors.append(f"{prefix}: evidence[{index}] must be a string")
                continue
            errors.extend(
                _validate_repository_path_field(
                    rel_path,
                    prefix=f"{prefix}: evidence[{index}]",
                    repo_root=repo_root,
                    require_exists=True,
                )
            )

    combined = _combined_text(entry)

    if change_type != "deviation_closure":
        for pattern in ETHICS_BYPASS_PATTERNS:
            if pattern.search(combined):
                errors.append(f"{prefix}: entry appears to bypass the ethics gate")

    if entry.get("collection_permitted") is True:
        errors.append(f"{prefix}: collection_permitted must not be set to true in a deviation entry")

    if entry.get("t11_verdict_override") == "PASS":
        errors.append(f"{prefix}: t11_verdict_override must not be PASS")

    if change_type == "deviation_closure":
        errors.extend(_validate_deviation_closure(entry, prefix=prefix, combined=combined))
    else:
        if change_type == "execution_order_exception" and isinstance(affected_tickets, list):
            if "T11" in affected_tickets:
                blocked_markers = (
                    "blocked",
                    "collection_permitted: false",
                    "collection_permitted false",
                )
                if not any(marker in combined.lower() for marker in blocked_markers):
                    errors.append(
                        f"{prefix}: execution_order_exception affecting T11 must preserve "
                        "BLOCKED semantics"
                    )
            if "T12" in affected_tickets:
                combined_lower = combined.lower()
                for phrase in T12_SCOPE_REQUIRED_PHRASES:
                    if phrase not in combined_lower:
                        errors.append(f"{prefix}: T12 scope must document {phrase!r}")
                for phrase in T12_SCOPE_PROHIBITED_PHRASES:
                    if phrase not in combined_lower:
                        errors.append(f"{prefix}: T12 scope must prohibit {phrase!r}")

        ethics_disclaimer = entry.get("ethics_disclaimer", "")
        if isinstance(ethics_disclaimer, str):
            disclaimer_lower = ethics_disclaimer.lower()
            if "institutional ethics determination remains pending" not in disclaimer_lower:
                errors.append(
                    f"{prefix}: ethics_disclaimer must state the institutional determination "
                    "remains pending"
                )
            if "does not constitute or imply institutional ethics approval" not in disclaimer_lower:
                errors.append(
                    f"{prefix}: ethics_disclaimer must state this is not institutional ethics "
                    "approval"
                )

    return errors


def validate_deviation_log(
    entries: list[dict[str, Any]],
    *,
    repo_root: Path | None = None,
    parse_errors: list[str] | None = None,
) -> list[str]:
    errors: list[str] = list(parse_errors or [])
    seen_ids: set[str] = set()
    for line_number, entry in enumerate(entries, start=1):
        entry_errors = validate_deviation_entry(entry, line_number=line_number, repo_root=repo_root)
        errors.extend(entry_errors)
        deviation_id = entry.get("deviation_id")
        if isinstance(deviation_id, str) and DEVIATION_ID_RE.fullmatch(deviation_id):
            if deviation_id in seen_ids:
                errors.append(f"line {line_number}: duplicate deviation_id {deviation_id!r}")
            seen_ids.add(deviation_id)
    return errors


def validate_deviation_log_path(relative_path: str) -> list[str]:
    if not is_tracked_governance_log_path(relative_path):
        return [f"deviation log must live under docs/governance/logs/: {relative_path!r}"]
    return []
