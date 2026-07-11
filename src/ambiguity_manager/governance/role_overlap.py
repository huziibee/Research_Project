"""Role overlap validation."""

from __future__ import annotations

from typing import Any

PROHIBITED_OVERLAPS = frozenset({"author_annotator", "annotator_adjudicator_same_record"})


def validate_role_overlap_entry(entry: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    roles = entry.get("roles")
    if not isinstance(roles, list) or len(roles) < 2:
        errors.append("roles must contain at least two role pseudonyms")

    overlap_type = entry.get("overlap_type")
    if overlap_type == "author_annotator":
        errors.append("author_annotator overlap is prohibited")
    if overlap_type == "annotator_adjudicator_same_record":
        errors.append("annotator cannot adjudicate their own record")

    if overlap_type == "author_adjudicator" and not entry.get("authority_approval_ref"):
        errors.append("author_adjudicator overlap requires authority_approval_ref")

    if entry.get("supervisor_participation") is True and entry.get("disclosed") is not True:
        errors.append("supervisor participation must be disclosed per record")

    return errors
