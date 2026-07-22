"""T14A blind annotation tooling foundations (synthetic-safe)."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ambiguity_manager.annotation.canonical import sha256_json
from ambiguity_manager.annotation.packages import read_jsonl, record_set_ids
from ambiguity_manager.annotation.roles import RolePolicyError, assert_official_annotator_role
from ambiguity_manager.annotation.schema import (
  ANNOTATION_SCHEMA_VERSION,
  HANDBOOK_VERSION,
  PACKAGE_VERSION,
)
from ambiguity_manager.annotation.validation import validate_annotator_response
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES


class AnnotationToolingError(ValueError):
  pass


CATEGORICAL_FIELDS = (
  "speech_act",
  "ambiguity_present",
  "risk_level",
  "capability_status",
  "recommended_strategy",
  "confidence",
)


def load_package(path: Path) -> list[dict[str, Any]]:
  records = read_jsonl(path)
  if not records:
    raise AnnotationToolingError(f"empty package: {path}")
  return records


def load_submissions(path: Path) -> dict[str, dict[str, Any]]:
  records = read_jsonl(path)
  by_id: dict[str, dict[str, Any]] = {}
  for record in records:
    errors = validate_annotator_response(record)
    if errors:
      raise AnnotationToolingError(
        f"invalid submission {record.get('record_id')}: " + "; ".join(errors)
      )
    rid = str(record["record_id"])
    if rid in by_id:
      raise AnnotationToolingError(f"duplicate submission for {rid}")
    by_id[rid] = record
  return by_id


def progress(package_ids: list[str], submissions: dict[str, dict[str, Any]]) -> dict[str, Any]:
  done = [rid for rid in package_ids if rid in submissions]
  missing = [rid for rid in package_ids if rid not in submissions]
  return {
    "n_expected": len(package_ids),
    "n_complete": len(done),
    "n_missing": len(missing),
    "complete_ids": sorted(done),
    "missing_ids": sorted(missing),
    "fraction_complete": (len(done) / len(package_ids)) if package_ids else 0.0,
  }


def assert_compatible_packages(package_a: list[dict[str, Any]], package_b: list[dict[str, Any]]) -> None:
  if record_set_ids(package_a) != record_set_ids(package_b):
    raise AnnotationToolingError("package record sets differ")
  for package in (package_a, package_b):
    for record in package:
      if record.get("handbook_version") != HANDBOOK_VERSION:
        raise AnnotationToolingError("handbook version mismatch in package")
      if record.get("annotation_schema_version") != ANNOTATION_SCHEMA_VERSION:
        raise AnnotationToolingError("annotation schema version mismatch in package")
      if record.get("package_version") != PACKAGE_VERSION:
        raise AnnotationToolingError("package version mismatch in package")


def _cohen_kappa(labels_a: list[Any], labels_b: list[Any]) -> float | None:
  if len(labels_a) != len(labels_b) or not labels_a:
    return None
  n = len(labels_a)
  agree = sum(1 for a, b in zip(labels_a, labels_b) if a == b)
  p_o = agree / n
  categories = sorted(set(labels_a) | set(labels_b), key=lambda x: str(x))
  count_a = Counter(labels_a)
  count_b = Counter(labels_b)
  p_e = sum((count_a[c] / n) * (count_b[c] / n) for c in categories)
  if p_e == 1.0:
    return 1.0 if p_o == 1.0 else 0.0
  return (p_o - p_e) / (1.0 - p_e)


def _jaccard(a: list[Any], b: list[Any]) -> float:
  sa, sb = set(a), set(b)
  if not sa and not sb:
    return 1.0
  return len(sa & sb) / len(sa | sb)


def compare_submissions(
  submissions_a: dict[str, dict[str, Any]],
  submissions_b: dict[str, dict[str, Any]],
) -> dict[str, Any]:
  shared = sorted(set(submissions_a) & set(submissions_b))
  missing_a = sorted(set(submissions_b) - set(submissions_a))
  missing_b = sorted(set(submissions_a) - set(submissions_b))
  disagreements: list[dict[str, Any]] = []
  field_agreements: dict[str, list[bool]] = {f: [] for f in CATEGORICAL_FIELDS}
  ambiguity_jaccards: list[float] = []
  cpc_slot_agreements: list[float] = []

  for rid in shared:
    a = submissions_a[rid]
    b = submissions_b[rid]
    record_disagreements: dict[str, Any] = {}
    for field in CATEGORICAL_FIELDS:
      same = a.get(field) == b.get(field)
      field_agreements[field].append(same)
      if not same:
        record_disagreements[field] = {"ANN-A": a.get(field), "ANN-B": b.get(field)}
    amb_j = _jaccard(a.get("ambiguity_types") or [], b.get("ambiguity_types") or [])
    ambiguity_jaccards.append(amb_j)
    if amb_j < 1.0:
      record_disagreements["ambiguity_types"] = {
        "ANN-A": a.get("ambiguity_types"),
        "ANN-B": b.get("ambiguity_types"),
        "jaccard": amb_j,
      }
    cpc_a = a.get("cpc") or {}
    cpc_b = b.get("cpc") or {}
    slot_same = 0
    for slot in CPC_SLOT_NAMES:
      if cpc_a.get(slot) == cpc_b.get(slot):
        slot_same += 1
    slot_frac = slot_same / len(CPC_SLOT_NAMES)
    cpc_slot_agreements.append(slot_frac)
    if slot_frac < 1.0:
      record_disagreements["cpc_slot_agreement"] = slot_frac
    if record_disagreements:
      disagreements.append({"record_id": rid, "disagreements": record_disagreements})

  categorical_raw = {
    field: (sum(vals) / len(vals) if vals else None)
    for field, vals in field_agreements.items()
  }
  kappas = {}
  for field in CATEGORICAL_FIELDS:
    labels_a = [submissions_a[rid].get(field) for rid in shared]
    labels_b = [submissions_b[rid].get(field) for rid in shared]
    kappas[field] = _cohen_kappa(labels_a, labels_b)

  confusion = {}
  for field in ("speech_act", "recommended_strategy", "risk_level", "capability_status"):
    matrix: dict[str, dict[str, int]] = {}
    for rid in shared:
      va = str(submissions_a[rid].get(field))
      vb = str(submissions_b[rid].get(field))
      matrix.setdefault(va, {})
      matrix[va][vb] = matrix[va].get(vb, 0) + 1
    confusion[field] = matrix

  return {
    "n_shared": len(shared),
    "missing_from_a": missing_a,
    "missing_from_b": missing_b,
    "raw_percent_agreement": categorical_raw,
    "cohen_kappa": kappas,
    "mean_ambiguity_jaccard": (
      sum(ambiguity_jaccards) / len(ambiguity_jaccards) if ambiguity_jaccards else None
    ),
    "mean_cpc_slot_agreement": (
      sum(cpc_slot_agreements) / len(cpc_slot_agreements) if cpc_slot_agreements else None
    ),
    "confusion_matrices": confusion,
    "disagreements": disagreements,
  }


def build_adjudication_queue(comparison: dict[str, Any]) -> list[dict[str, Any]]:
  queue: list[dict[str, Any]] = []
  for item in comparison.get("disagreements", []):
    queue.append(
      {
        "record_id": item["record_id"],
        "status": "unresolved",
        "disagreement_summary": item["disagreements"],
        "adjudicator_role": None,
        "adjudication_decision": None,
        "rationale": None,
        "timestamp": None,
        "handbook_version": HANDBOOK_VERSION,
        "annotation_schema_version": ANNOTATION_SCHEMA_VERSION,
        "package_version": PACKAGE_VERSION,
      }
    )
  return queue


@dataclass
class GoldExportGate:
  submissions_a: dict[str, dict[str, Any]]
  submissions_b: dict[str, dict[str, Any]]
  adjudication_records: list[dict[str, Any]]
  package_hash_a: str
  package_hash_b: str
  expected_package_hash_a: str
  expected_package_hash_b: str


def _disagrees(a: dict[str, Any], b: dict[str, Any]) -> bool:
  if any(a.get(f) != b.get(f) for f in CATEGORICAL_FIELDS):
    return True
  if set(a.get("ambiguity_types") or []) != set(b.get("ambiguity_types") or []):
    return True
  return (a.get("cpc") or {}) != (b.get("cpc") or {})


def validate_gold_export_gate(gate: GoldExportGate) -> list[str]:
  errors: list[str] = []
  if gate.package_hash_a != gate.expected_package_hash_a:
    errors.append("ANN-A package hash mismatch")
  if gate.package_hash_b != gate.expected_package_hash_b:
    errors.append("ANN-B package hash mismatch")
  shared = set(gate.submissions_a) & set(gate.submissions_b)
  if set(gate.submissions_a) != set(gate.submissions_b):
    errors.append("missing annotation on one side")
  by_id = {r["record_id"]: r for r in gate.adjudication_records}
  for rid in sorted(shared):
    a = gate.submissions_a[rid]
    b = gate.submissions_b[rid]
    if not _disagrees(a, b):
      continue
    adj = by_id.get(rid)
    if adj is None:
      errors.append(f"{rid}: disagreement missing adjudication record")
      continue
    if adj.get("status") != "resolved":
      errors.append(f"{rid}: adjudication unresolved")
    if not adj.get("adjudication_decision"):
      errors.append(f"{rid}: adjudication decision missing")
    role = adj.get("adjudicator_role")
    if role in {None, "AUTHOR-01", "ADJ-01"} or role == "unresolved":
      errors.append(f"{rid}: invalid or unresolved adjudicator role")
    if adj.get("retains_originals") is not True:
      if adj.get("ANN-A_original") is None or adj.get("ANN-B_original") is None:
        errors.append(f"{rid}: adjudication must retain both originals")
    if adj.get("handbook_version") != HANDBOOK_VERSION:
      errors.append(f"{rid}: adjudication handbook version mismatch")
    if adj.get("annotation_schema_version") != ANNOTATION_SCHEMA_VERSION:
      errors.append(f"{rid}: adjudication schema version mismatch")
  return errors


def export_synthetic_gold(
  gate: GoldExportGate,
  *,
  allow_real_partitions: bool = False,
) -> list[dict[str, Any]]:
  errors = validate_gold_export_gate(gate)
  if errors:
    raise AnnotationToolingError("gold export blocked: " + "; ".join(errors))
  gold: list[dict[str, Any]] = []
  adj_by_id = {r["record_id"]: r for r in gate.adjudication_records}
  for rid in sorted(set(gate.submissions_a) & set(gate.submissions_b)):
    a = gate.submissions_a[rid]
    b = gate.submissions_b[rid]
    partition = a.get("dataset_partition") or b.get("dataset_partition")
    if partition in {"calibration", "main"} and not allow_real_partitions:
      raise AnnotationToolingError(
        "refusing to export calibration/main records as gold in T14A foundation task"
      )
    decision = adj_by_id.get(rid, {}).get("adjudication_decision")
    if decision is None:
      # perfect agreement path: use A (== B for compared fields)
      decision = {
        "speech_act": a.get("speech_act"),
        "risk_level": a.get("risk_level"),
        "capability_status": a.get("capability_status"),
        "recommended_strategy": a.get("recommended_strategy"),
        "ambiguity_types": a.get("ambiguity_types"),
        "cpc": a.get("cpc"),
      }
    gold.append(
      {
        "record_id": rid,
        "record_class": "adjudicated_gold",
        "label_confidence": "manual_gold",
        "ANN-A_original_sha256": sha256_json(a),
        "ANN-B_original_sha256": sha256_json(b),
        "final_labels": decision,
        "synthetic": True,
      }
    )
  return gold


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("w", encoding="utf-8") as handle:
    for record in records:
      handle.write(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
      handle.write("\n")
