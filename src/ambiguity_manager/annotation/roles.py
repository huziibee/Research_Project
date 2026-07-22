"""Role-policy validation for the annotation programme."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ambiguity_manager.annotation.schema import load_roles


class RolePolicyError(ValueError):
  pass


def authorised_annotator_roles(root: Path | None = None) -> set[str]:
  roles = load_roles(str(root) if root else None)
  return set(roles["authorised_official_annotator_pseudonyms"])


def assert_official_annotator_role(role: str, root: Path | None = None) -> None:
  allowed = authorised_annotator_roles(root)
  if role not in allowed:
    raise RolePolicyError(
      f"official annotator role {role!r} is not authorised; expected one of {sorted(allowed)}"
    )


def assert_not_author_as_annotator(role: str, person_name: str | None = None, root: Path | None = None) -> None:
  roles = load_roles(str(root) if root else None)
  author = roles["roles"]["AUTHOR-01"]
  if role in {"ANN-A", "ANN-B"} and person_name == author["person_name"]:
    raise RolePolicyError("Mohammed Bangie cannot be assigned as ANN-A or ANN-B")
  if role in author.get("prohibited", []):
    raise RolePolicyError(f"role {role!r} prohibited for author")
  if not author.get("may_be_annotator_a", False) and role == "ANN-A":
    # author config already forbids; block assigning AUTHOR-01 identity to ANN roles
    pass
  prohibited_names = set(roles.get("prohibited_official_annotator_names", []))
  if person_name in prohibited_names and role in {"ANN-A", "ANN-B"}:
    raise RolePolicyError(f"{person_name} cannot be an official annotator")


def validate_assignment_payload(payload: dict[str, Any], root: Path | None = None) -> list[str]:
  errors: list[str] = []
  roles = load_roles(str(root) if root else None)
  annotator_role = payload.get("annotator_role")
  person_name = payload.get("person_name")
  try:
    assert_official_annotator_role(str(annotator_role), root=root)
  except RolePolicyError as exc:
    errors.append(str(exc))
  if person_name in set(roles.get("prohibited_official_annotator_names", [])):
    errors.append(f"{person_name} cannot be assigned as an official annotator")
  if roles.get("external_annotators_permitted") is False:
    allowed_names = set(roles.get("authorised_official_annotator_names", []))
    if person_name is not None and person_name not in allowed_names:
      errors.append(f"external or unauthorised annotator name {person_name!r}")
  if annotator_role == "AUTHOR-01":
    errors.append("AUTHOR-01 cannot be used as an official annotator role")
  return errors


def validate_roles_config(root: Path | None = None) -> list[str]:
  roles = load_roles(str(root) if root else None)
  errors: list[str] = []
  author = roles["roles"]["AUTHOR-01"]
  if author.get("may_be_annotator_a") or author.get("may_be_annotator_b"):
    errors.append("AUTHOR-01 must not be permitted as ANN-A/ANN-B")
  if author.get("handbook_and_synthetic_labels_enter_official_gold"):
    errors.append("author handbook/synthetic labels must not enter official gold")
  if roles.get("external_annotators_permitted") is not False:
    errors.append("external annotators must remain forbidden")
  if roles["roles"]["ADJ-01"].get("status") != "unresolved":
    errors.append("ADJ-01 must remain unresolved until T14 adjudication policy")
  return errors
