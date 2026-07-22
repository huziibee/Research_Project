"""Package building, hashing, and A/B ordering."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from ambiguity_manager.annotation.canonical import dumps_jsonl_record, sha256_hex, sha256_json
from ambiguity_manager.annotation.schema import (
  ANNOTATION_SCHEMA_VERSION,
  HANDBOOK_VERSION,
  PACKAGE_VERSION,
)
from ambiguity_manager.annotation.validation import (
  AnnotationValidationError,
  validate_annotator_package_record,
  validate_candidate_record,
)

HIDDEN_KEYS = (
  "hidden",
  "design_cell",
  "seed_id",
  "template_id",
  "group_id",
  "author_notes",
  "review_codes",
  "intended_answer",
  "model_output",
  "model_critique",
  "author_expectation",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
  records: list[dict[str, Any]] = []
  with path.open(encoding="utf-8") as handle:
    for line_number, line in enumerate(handle, start=1):
      stripped = line.strip()
      if not stripped:
        continue
      payload = json.loads(stripped)
      if not isinstance(payload, dict):
        raise AnnotationValidationError(f"{path}: line {line_number} is not an object")
      records.append(payload)
  return records


def write_jsonl(path: Path, records: list[dict[str, Any]], *, overwrite: bool = False) -> str:
  if path.exists() and not overwrite:
    raise FileExistsError(f"refusing to overwrite frozen package: {path}")
  path.parent.mkdir(parents=True, exist_ok=True)
  lines = [dumps_jsonl_record(record) for record in records]
  body = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
  path.write_bytes(body)
  return sha256_hex(body)


def strip_hidden_fields(record: dict[str, Any]) -> dict[str, Any]:
  visible = {
    "record_id": record["record_id"],
    "command": record["command"],
    "dialogue_history": list(record.get("dialogue_history") or []),
    "scene_context": record.get("scene_context"),
    "capability_context": record.get("capability_context"),
    "visible_provenance_category": record["visible_provenance_category"],
    "package_version": record.get("package_version", PACKAGE_VERSION),
    "handbook_version": record.get("handbook_version", HANDBOOK_VERSION),
    "annotation_schema_version": record.get(
      "annotation_schema_version", ANNOTATION_SCHEMA_VERSION
    ),
    "dataset_partition": record["dataset_partition"],
  }
  return visible


def deterministic_order(record_ids: list[str], *, package_id: str) -> list[str]:
  ordered = list(record_ids)
  rng = random.Random(sha256_hex(package_id.encode("utf-8")))
  rng.shuffle(ordered)
  return ordered


def build_annotator_package(
  source_records: list[dict[str, Any]],
  *,
  annotator_role: str,
  package_id: str,
) -> list[dict[str, Any]]:
  for record in source_records:
    errors = validate_candidate_record(record, require_hidden=True)
    if errors:
      raise AnnotationValidationError(
        f"{record.get('record_id')}: " + "; ".join(errors)
      )
  ids = [str(r["record_id"]) for r in source_records]
  if len(ids) != len(set(ids)):
    raise AnnotationValidationError("duplicate record_id in source package")
  by_id = {str(r["record_id"]): r for r in source_records}
  ordered_ids = deterministic_order(ids, package_id=package_id)
  package_records: list[dict[str, Any]] = []
  for index, record_id in enumerate(ordered_ids):
    visible = strip_hidden_fields(by_id[record_id])
    visible["package_id"] = package_id
    visible["annotator_role"] = annotator_role
    visible["record_order_index"] = index
    errors = validate_annotator_package_record(visible)
    # package_id / annotator_role / record_order_index are package metadata extras
    errors = [e for e in errors if not e.startswith("missing required candidate field")]
    # re-validate core visible fields only
    core_errors = []
    for field in (
      "record_id",
      "command",
      "dialogue_history",
      "scene_context",
      "capability_context",
      "visible_provenance_category",
      "package_version",
      "handbook_version",
      "annotation_schema_version",
      "dataset_partition",
    ):
      if field not in visible:
        core_errors.append(f"missing {field}")
    if "hidden" in visible:
      core_errors.append("hidden leaked")
    if core_errors:
      raise AnnotationValidationError("; ".join(core_errors))
    package_records.append(visible)
  return package_records


def package_bytes_hash(records: list[dict[str, Any]]) -> str:
  return sha256_hex(("\n".join(dumps_jsonl_record(r) for r in records) + "\n").encode("utf-8"))


def record_set_ids(records: list[dict[str, Any]]) -> list[str]:
  return sorted(str(r["record_id"]) for r in records)


def assert_same_record_set(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> None:
  if record_set_ids(a) != record_set_ids(b):
    raise AnnotationValidationError("ANN-A and ANN-B packages must contain the same record IDs")


def detect_mutation(path: Path, expected_hash: str) -> bool:
  digest = sha256_hex(path.read_bytes())
  return digest != expected_hash
