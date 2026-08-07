"""Pilot-120 v1 freeze, hashing, and evaluation-only loader guards.

Pilot-120 may be frozen only after final-protocol independent annotation and
adjudication gates are closed. The loader refuses training/dev use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ambiguity_manager.annotation.canonical import sha256_hex, sha256_json
from ambiguity_manager.annotation.final_protocol_v7 import (
  PILOT_120_N,
  PROTOCOL_ID,
  PROTOCOL_VERSION,
  FinalProtocolError,
  assert_blind_package,
  build_blind_packages,
  capability_class_distribution,
  compute_final_protocol_agreement,
  file_sha256,
  load_final_protocol_config,
  one_path_determinacy,
  read_jsonl,
  validate_pilot_120_source_subset,
  write_json,
  write_jsonl,
)
from ambiguity_manager.paths import ProjectPaths

PILOT_120_SET_ID = "pilot_120_v1"
EVAL_ONLY_DESIGNATION = "evaluation_only"


class Pilot120FreezeError(ValueError):
  pass


class Pilot120LoaderError(ValueError):
  pass


@dataclass(frozen=True)
class Pilot120Paths:
  root: Path

  @property
  def artifact_root(self) -> Path:
    return self.root / "data" / "annotations" / PILOT_120_SET_ID

  @property
  def source_canonical(self) -> Path:
    return self.artifact_root / "source_canonical.jsonl"

  @property
  def blind_a(self) -> Path:
    return self.artifact_root / "blind_packages" / "ANN-A.jsonl"

  @property
  def blind_b(self) -> Path:
    return self.artifact_root / "blind_packages" / "ANN-B.jsonl"

  @property
  def submissions_a(self) -> Path:
    return self.artifact_root / "annotations_raw" / "ANN-A.jsonl"

  @property
  def submissions_b(self) -> Path:
    return self.artifact_root / "annotations_raw" / "ANN-B.jsonl"

  @property
  def disagreements(self) -> Path:
    return self.artifact_root / "adjudication" / "disagreements.jsonl"

  @property
  def adjudication(self) -> Path:
    return self.artifact_root / "adjudication" / "decisions.jsonl"

  @property
  def agreement_report(self) -> Path:
    return self.artifact_root / "reports" / "final_protocol_agreement.json"

  @property
  def final_gold(self) -> Path:
    return self.artifact_root / "final_gold.jsonl"

  @property
  def manifest(self) -> Path:
    return self.artifact_root / "manifest.json"

  @property
  def hashes(self) -> Path:
    return self.artifact_root / "hashes.json"

  @property
  def freeze_report(self) -> Path:
    return self.artifact_root / "freeze_report.json"

  @property
  def status(self) -> Path:
    return self.artifact_root / "STATUS.json"

  @property
  def eval_handoff(self) -> Path:
    return self.root / "configs" / "evaluation" / "pilot_120_v1_eval_handoff.json"

  @property
  def protocol_config(self) -> Path:
    return self.root / "configs" / "annotation" / "final_protocol_v7.json"

  @property
  def eval_config(self) -> Path:
    return self.root / "configs" / "evaluation" / "pilot_120_v1.json"


def pilot_120_paths(root: Path | None = None) -> Pilot120Paths:
  base = ProjectPaths.from_repo_root() if root is None else ProjectPaths(root=root)
  return Pilot120Paths(root=base.root)


def discover_prerequisite_artifacts(root: Path | None = None) -> dict[str, Any]:
  """Inspect whether assumed semantic-QA / 120-subset artifacts exist."""
  paths = ProjectPaths.from_repo_root() if root is None else ProjectPaths(root=root)
  candidates = {
    "FINAL_SEMANTIC_QA_REPORT.md": paths.root / "FINAL_SEMANTIC_QA_REPORT.md",
    "docs/DEFERRED_FULL_1000_SEMANTIC_QA_NOTES.md": (
      paths.docs / "DEFERRED_FULL_1000_SEMANTIC_QA_NOTES.md"
    ),
    "annotations/manual_kappa_v7_final_protocol/README.md": (
      paths.root / "annotations" / "manual_kappa_v7_final_protocol" / "README.md"
    ),
    "tests/test_compound_ambiguity_v7_qa.py": (
      paths.tests / "test_compound_ambiguity_v7_qa.py"
    ),
    "data/annotations/pilot_120_v1/source_canonical.jsonl": (
      paths.data_annotations / PILOT_120_SET_ID / "source_canonical.jsonl"
    ),
  }
  found = {key: path.is_file() for key, path in candidates.items()}
  return {
    "assumed_artifacts": found,
    "all_present": all(found.values()),
    "missing": sorted(k for k, ok in found.items() if not ok),
  }


def current_freeze_blockers(root: Path | None = None) -> list[str]:
  p = pilot_120_paths(root)
  blockers: list[str] = []
  if not p.source_canonical.is_file():
    blockers.append("missing source_canonical.jsonl (120-record repaired subset)")
  else:
    records = read_jsonl(p.source_canonical)
    blockers.extend(validate_pilot_120_source_subset(records))
  if not p.submissions_a.is_file() or not p.submissions_b.is_file():
    blockers.append("missing independent final-protocol ANN-A/ANN-B submissions")
  else:
    a = {r["record_id"]: r for r in read_jsonl(p.submissions_a)}
    b = {r["record_id"]: r for r in read_jsonl(p.submissions_b)}
    if len(a) != PILOT_120_N or len(b) != PILOT_120_N:
      blockers.append("final-protocol submissions incomplete for 120 records")
  if p.final_gold.is_file():
    gold = read_jsonl(p.final_gold)
    if len(gold) != PILOT_120_N:
      blockers.append(f"final_gold has {len(gold)} records, expected {PILOT_120_N}")
  else:
    blockers.append("final_gold not produced (adjudication/export incomplete)")
  if p.manifest.is_file():
    manifest = json.loads(p.manifest.read_text(encoding="utf-8"))
    if manifest.get("status") != "frozen":
      blockers.append(f"manifest status is {manifest.get('status')!r}, not frozen")
    if manifest.get("evaluation_only") is not True:
      blockers.append("manifest not marked evaluation_only")
  else:
    blockers.append("Pilot-120 manifest missing")
  # Human gates: supervisor annotation required; ADJ role may still be unresolved in roles config
  roles_path = p.root / "configs" / "annotation" / "annotation_roles_v1.json"
  if roles_path.is_file():
    roles = json.loads(roles_path.read_text(encoding="utf-8"))
    adj = roles.get("roles", {}).get("ADJ-01", {})
    if adj.get("status") == "unresolved":
      blockers.append("ADJ-01 adjudicator identity unresolved in annotation_roles_v1.json")
  return blockers


def initialize_artifact_tree(root: Path | None = None) -> Pilot120Paths:
  p = pilot_120_paths(root)
  for path in (
    p.artifact_root,
    p.artifact_root / "blind_packages",
    p.artifact_root / "annotations_raw",
    p.artifact_root / "adjudication",
    p.artifact_root / "reports",
  ):
    path.mkdir(parents=True, exist_ok=True)
  return p


def prepare_blind_packages_from_source(root: Path | None = None) -> dict[str, Any]:
  p = initialize_artifact_tree(root)
  if not p.source_canonical.is_file():
    raise Pilot120FreezeError("source_canonical.jsonl missing; cannot build blind packages")
  records = read_jsonl(p.source_canonical)
  errors = validate_pilot_120_source_subset(records)
  # Allow package prep even if one_path labels incomplete, but refuse D>0 and wrong N
  hard = [e for e in errors if "capability class D" in e or "expected 120" in e or "not unique" in e]
  if hard:
    raise Pilot120FreezeError("; ".join(hard))
  package_a, package_b = build_blind_packages(records)
  assert_blind_package(package_a)
  assert_blind_package(package_b)
  write_jsonl(p.blind_a, package_a)
  write_jsonl(p.blind_b, package_b)
  return {
    "n": len(records),
    "ann_a_path": str(p.blind_a),
    "ann_b_path": str(p.blind_b),
    "ann_a_sha256": file_sha256(p.blind_a),
    "ann_b_sha256": file_sha256(p.blind_b),
  }


def _submissions_by_id(path: Path) -> dict[str, dict[str, Any]]:
  records = read_jsonl(path)
  by_id: dict[str, dict[str, Any]] = {}
  for record in records:
    rid = str(record["record_id"])
    if rid in by_id:
      raise Pilot120FreezeError(f"duplicate submission for {rid}")
    by_id[rid] = record
  return by_id


def run_agreement_and_queue(root: Path | None = None) -> dict[str, Any]:
  p = pilot_120_paths(root)
  a = _submissions_by_id(p.submissions_a)
  b = _submissions_by_id(p.submissions_b)
  if set(a) != set(b):
    raise Pilot120FreezeError("ANN-A and ANN-B record sets differ")
  agreement = compute_final_protocol_agreement(a, b)
  write_json(p.agreement_report, agreement)

  disagreements: list[dict[str, Any]] = []
  compare_fields = (
    "ambiguity_types",
    "capability_status",
    "capability_interpretation",
    "risk_level",
    "speech_act",
  )
  for rid in sorted(a):
    ra, rb = a[rid], b[rid]
    fields: list[str] = []
    term_a = ra.get("terminal_strategy", ra.get("recommended_strategy"))
    term_b = rb.get("terminal_strategy", rb.get("recommended_strategy"))
    if term_a != term_b:
      fields.append("terminal_strategy")
    for field in compare_fields:
      va = ra.get(field)
      vb = rb.get(field)
      if field == "ambiguity_types":
        if set(va or []) != set(vb or []):
          fields.append(field)
      elif va != vb:
        fields.append(field)
    if fields:
      ann_a_view = {f: (set(ra.get(f) or []) if f == "ambiguity_types" else ra.get(f)) for f in fields}
      ann_b_view = {f: (set(rb.get(f) or []) if f == "ambiguity_types" else rb.get(f)) for f in fields}
      if "terminal_strategy" in fields:
        ann_a_view["terminal_strategy"] = term_a
        ann_b_view["terminal_strategy"] = term_b
      disagreements.append(
        {
          "record_id": rid,
          "disagreement_fields": fields,
          "ANN-A": {k: (sorted(v) if isinstance(v, set) else v) for k, v in ann_a_view.items()},
          "ANN-B": {k: (sorted(v) if isinstance(v, set) else v) for k, v in ann_b_view.items()},
          "status": "unresolved",
        }
      )
  write_jsonl(p.disagreements, disagreements)
  return {
    "agreement": agreement,
    "disagreement_count": len(disagreements),
    "disagreements_path": str(p.disagreements),
  }


def _merge_gold_record(
  source: dict[str, Any],
  ann_a: dict[str, Any],
  ann_b: dict[str, Any],
  adjudication: dict[str, Any] | None,
) -> dict[str, Any]:
  if adjudication and adjudication.get("status") == "resolved":
    labels = dict(adjudication.get("adjudication_decision") or {})
  else:
    # Perfect agreement path
    labels = {
      "speech_act": ann_a.get("speech_act"),
      "terminal_strategy": ann_a.get("terminal_strategy", ann_a.get("recommended_strategy")),
      "recommended_strategy": ann_a.get("recommended_strategy", ann_a.get("terminal_strategy")),
      "ambiguity_types": list(ann_a.get("ambiguity_types") or []),
      "capability_status": ann_a.get("capability_status"),
      "capability_interpretation": ann_a.get("capability_interpretation"),
      "risk_level": ann_a.get("risk_level"),
    }
  term = labels.get("terminal_strategy") or labels.get("recommended_strategy")
  labels["terminal_strategy"] = term
  labels["recommended_strategy"] = labels.get("recommended_strategy") or term
  cap_class = source.get("capability_evidence_class")
  if cap_class is None:
    from ambiguity_manager.annotation.final_protocol_v7 import classify_capability_evidence

    cap_class = classify_capability_evidence(source)
  determinacy = one_path_determinacy(source, labels)
  gold = {
    "record_id": source["record_id"],
    "schema_version": source.get("schema_version", "2.0.0"),
    "command": source.get("command"),
    "scene_context": source.get("scene_context"),
    "dialogue_history": source.get("dialogue_history") or [],
    "capability_context": source.get("capability_context"),
    "group_id": source.get("group_id"),
    "record_class": "adjudicated_gold",
    "label_confidence": "manual_gold",
    "evaluation_only": True,
    "pilot_120_set_id": PILOT_120_SET_ID,
    "protocol_id": PROTOCOL_ID,
    "protocol_version": PROTOCOL_VERSION,
    "speech_act": labels.get("speech_act"),
    "terminal_strategy": labels.get("terminal_strategy"),
    "recommended_strategy": labels.get("recommended_strategy"),
    "ambiguity_types": list(labels.get("ambiguity_types") or []),
    "capability_status": labels.get("capability_status"),
    "capability_interpretation": labels.get("capability_interpretation"),
    "risk_level": labels.get("risk_level"),
    "capability_evidence_class": cap_class,
    "one_path_determinacy": bool(determinacy),
    "ANN-A_original_sha256": sha256_json(ann_a),
    "ANN-B_original_sha256": sha256_json(ann_b),
  }
  return gold


def export_final_gold(root: Path | None = None) -> list[dict[str, Any]]:
  p = pilot_120_paths(root)
  sources = {r["record_id"]: r for r in read_jsonl(p.source_canonical)}
  a = _submissions_by_id(p.submissions_a)
  b = _submissions_by_id(p.submissions_b)
  if set(sources) != set(a) or set(sources) != set(b):
    raise Pilot120FreezeError("source/annotation id sets must match exactly")
  adj_records = read_jsonl(p.adjudication) if p.adjudication.is_file() else []
  adj_by_id = {r["record_id"]: r for r in adj_records}

  # Ensure disagreements resolved
  disagreements = read_jsonl(p.disagreements) if p.disagreements.is_file() else []
  for item in disagreements:
    rid = item["record_id"]
    adj = adj_by_id.get(rid)
    if adj is None or adj.get("status") != "resolved" or not adj.get("adjudication_decision"):
      raise Pilot120FreezeError(f"unresolved adjudication for {rid}")
    if adj.get("ANN-A_original") is None or adj.get("ANN-B_original") is None:
      raise Pilot120FreezeError(f"adjudication for {rid} must retain ANN-A/ANN-B originals")

  gold = [
    _merge_gold_record(sources[rid], a[rid], b[rid], adj_by_id.get(rid))
    for rid in sorted(sources)
  ]
  for record in gold:
    if record.get("capability_evidence_class") == "D":
      raise Pilot120FreezeError(f"{record['record_id']}: capability D forbidden in Pilot-120")
    if record.get("one_path_determinacy") is not True:
      raise Pilot120FreezeError(f"{record['record_id']}: one_path_determinacy must be true")
  write_jsonl(p.final_gold, gold)
  return gold


def _load_train_dev_ids(root: Path) -> set[str]:
  ids: set[str] = set()
  splits = root / "data" / "development" / "source_splits_v1" / "record_manifest.jsonl"
  if splits.is_file():
    for row in read_jsonl(splits):
      split = str(row.get("split") or row.get("partition") or "").lower()
      if split in {"train", "dev", "development", "validation"}:
        rid = row.get("record_id") or row.get("id")
        if rid:
          ids.add(str(rid))
  # Also exclude T13 calibration ids from train/dev confusion
  cal = root / "data" / "annotations" / "t13" / "calibration" / "candidates_source.jsonl"
  if cal.is_file():
    for row in read_jsonl(cal):
      if row.get("record_id"):
        ids.add(str(row["record_id"]))
  return ids


def compute_hashes(root: Path | None = None) -> dict[str, str]:
  p = pilot_120_paths(root)
  hashes: dict[str, str] = {}
  mapping = {
    "source_canonical": p.source_canonical,
    "annotations_raw_ANN-A": p.submissions_a,
    "annotations_raw_ANN-B": p.submissions_b,
    "final_gold": p.final_gold,
    "manifest": p.manifest,
    "final_protocol_config": p.protocol_config,
    "eval_config": p.eval_config,
    "agreement_report": p.agreement_report,
  }
  for key, path in mapping.items():
    if path.is_file():
      hashes[key] = file_sha256(path)
  hashes["hashes_algorithm"] = "sha256"
  return hashes


def freeze_pilot_120_v1(*, root: Path | None = None, force: bool = False) -> dict[str, Any]:
  """Freeze Pilot-120 only when all gates are closed."""
  if force:
    raise Pilot120FreezeError("force freeze is disabled for Pilot-120 integrity")
  p = initialize_artifact_tree(root)
  blockers = current_freeze_blockers(p.root)
  # Ignore artefacts this function is about to create; enforce all other gates.
  substantive = [
    b
    for b in blockers
    if not b.startswith("Pilot-120 manifest")
    and not b.startswith("manifest status")
    and b != "final_gold not produced (adjudication/export incomplete)"
  ]
  if substantive:
    raise Pilot120FreezeError("freeze blocked: " + "; ".join(substantive))
  run_agreement_and_queue(p.root)
  gold = export_final_gold(p.root)

  # Leakage
  train_dev = _load_train_dev_ids(p.root)
  gold_ids = [r["record_id"] for r in gold]
  overlap = sorted(set(gold_ids) & train_dev)
  if overlap:
    raise Pilot120FreezeError(f"train/dev leakage: {overlap[:5]}")

  dist = capability_class_distribution(gold)
  if dist.get("D", 0) != 0:
    raise Pilot120FreezeError("capability D must be 0 at freeze")
  if any(r.get("one_path_determinacy") is not True for r in gold):
    raise Pilot120FreezeError("one_path_determinacy must be true for all 120")

  agreement = json.loads(p.agreement_report.read_text(encoding="utf-8"))
  disagreements = read_jsonl(p.disagreements)

  manifest = {
    "evaluation_set_id": PILOT_120_SET_ID,
    "status": "frozen",
    "evaluation_only": True,
    "forbid_training_load": True,
    "forbid_dev_tuning": True,
    "designation": EVAL_ONLY_DESIGNATION,
    "n_records": PILOT_120_N,
    "record_ids": gold_ids,
    "deterministic_ordering": "sorted(record_id)",
    "protocol_id": PROTOCOL_ID,
    "protocol_version": PROTOCOL_VERSION,
    "capability_class_distribution": dist,
    "one_path_determinacy_true_count": sum(
      1 for r in gold if r.get("one_path_determinacy") is True
    ),
    "agreement_summary": {
      "terminal_strategy": agreement.get("terminal_strategy"),
      "ambiguity_types": agreement.get("ambiguity_types"),
      "capability_status": agreement.get("capability_status"),
    },
    "pilot_annotation_agreement": agreement.get("pilot_annotation_agreement"),
    "disagreement_count": len(disagreements),
    "adjudication_count": len(disagreements),
    "paths": {
      "source_canonical": str(p.source_canonical.relative_to(p.root)),
      "final_gold": str(p.final_gold.relative_to(p.root)),
      "hashes": str(p.hashes.relative_to(p.root)),
    },
  }
  write_json(p.manifest, manifest)
  hashes = compute_hashes(p.root)
  # include manifest hash after write
  hashes["manifest"] = file_sha256(p.manifest)
  hashes["final_gold"] = file_sha256(p.final_gold)
  write_json(p.hashes, hashes)
  # rewrite hashes into manifest
  manifest["sha256"] = hashes
  write_json(p.manifest, manifest)
  hashes["manifest"] = file_sha256(p.manifest)
  write_json(p.hashes, hashes)

  freeze_report = {
    "evaluation_set_id": PILOT_120_SET_ID,
    "status": "FROZEN",
    "statement": (
      "Pilot-120 v1: FINAL-PROTOCOL ANNOTATED, ADJUDICATED, FROZEN, HASHED, EVALUATION-ONLY"
    ),
    "full_1000_statement": "Full-1000: NOT READY TO FREEZE",
    "n_records": PILOT_120_N,
    "capability_class_distribution": dist,
    "one_path_determinacy": {
      "true_count": PILOT_120_N,
      "required": True,
    },
    "agreement": agreement,
    "disagreement_count": len(disagreements),
    "sha256": hashes,
  }
  write_json(p.freeze_report, freeze_report)
  write_json(
    p.status,
    {
      "pilot_120_v1": "FINAL-PROTOCOL ANNOTATED, ADJUDICATED, FROZEN, HASHED, EVALUATION-ONLY",
      "full_1000": "NOT READY TO FREEZE",
      "frozen": True,
    },
  )
  write_eval_handoff(p.root, hashes=hashes)
  return freeze_report


def write_eval_handoff(root: Path | None = None, hashes: dict[str, str] | None = None) -> Path:
  p = pilot_120_paths(root)
  hashes = hashes or (json.loads(p.hashes.read_text(encoding="utf-8")) if p.hashes.is_file() else {})
  handoff = {
    "evaluation_set_id": PILOT_120_SET_ID,
    "evaluation_only": True,
    "forbid_training_load": True,
    "inputs": {
      "gold": str(p.final_gold.relative_to(p.root)),
      "manifest": str(p.manifest.relative_to(p.root)),
      "config": str(p.eval_config.relative_to(p.root)),
    },
    "excluded_inputs": [
      "pilot annotation files",
      "private owner QA",
      "adjudication rationale",
      "ANN-A/ANN-B raw packages (scoring uses final_gold only)",
    ],
    "command": (
      "python3 -m ambiguity_manager.evaluation.pilot_120_cli evaluate "
      "--config configs/evaluation/pilot_120_v1.json "
      "--predictions <PREDICTIONS.jsonl>"
    ),
    "sha256": {
      "final_gold": hashes.get("final_gold"),
      "manifest": hashes.get("manifest"),
      "eval_config": hashes.get("eval_config"),
      "final_protocol_config": hashes.get("final_protocol_config"),
    },
  }
  write_json(p.eval_handoff, handoff)
  return p.eval_handoff


def write_blocked_status(root: Path | None = None) -> dict[str, Any]:
  p = initialize_artifact_tree(root)
  blockers = current_freeze_blockers(p.root)
  discovery = discover_prerequisite_artifacts(p.root)
  status = {
    "pilot_120_v1": "NOT FROZEN — final-protocol gates open / prerequisites missing",
    "full_1000": "NOT READY TO FREEZE",
    "frozen": False,
    "blockers": blockers,
    "prerequisite_discovery": discovery,
    "protocol_id": PROTOCOL_ID,
    "protocol_version": PROTOCOL_VERSION,
  }
  write_json(p.status, status)
  # Keep eval config status honest
  eval_cfg = json.loads(p.eval_config.read_text(encoding="utf-8"))
  eval_cfg["status"] = "not_frozen"
  write_json(p.eval_config, eval_cfg)
  return status


def load_pilot_120_for_evaluation(
  *,
  root: Path | None = None,
  purpose: str,
) -> list[dict[str, Any]]:
  """Load Pilot-120 gold for evaluation only.

  Raises if purpose indicates training/dev/tuning use, or if freeze is not complete.
  """
  purpose_norm = purpose.strip().lower()
  forbidden = {
    "train",
    "training",
    "dev",
    "development",
    "tuning",
    "finetune",
    "fine-tune",
    "qlora",
    "prompt_tuning",
    "threshold_tuning",
  }
  if purpose_norm in forbidden or any(tok in purpose_norm for tok in forbidden):
    raise Pilot120LoaderError(
      f"refusing to load pilot_120_v1 for purpose={purpose!r}; evaluation-only"
    )
  if purpose_norm not in {"evaluation", "eval", "scoring", "official_evaluation"}:
    raise Pilot120LoaderError(
      f"unsupported purpose {purpose!r}; allowed: evaluation/eval/scoring/official_evaluation"
    )
  p = pilot_120_paths(root)
  if not p.manifest.is_file() or not p.final_gold.is_file():
    raise Pilot120LoaderError("Pilot-120 is not frozen; final_gold/manifest missing")
  manifest = json.loads(p.manifest.read_text(encoding="utf-8"))
  if manifest.get("status") != "frozen":
    raise Pilot120LoaderError("Pilot-120 manifest is not frozen")
  if manifest.get("evaluation_only") is not True or manifest.get("forbid_training_load") is not True:
    raise Pilot120LoaderError("Pilot-120 missing evaluation-only guards")
  gold = read_jsonl(p.final_gold)
  if len(gold) != PILOT_120_N:
    raise Pilot120LoaderError(f"expected {PILOT_120_N} gold records, found {len(gold)}")
  # Verify hash if present
  if p.hashes.is_file():
    hashes = json.loads(p.hashes.read_text(encoding="utf-8"))
    actual = file_sha256(p.final_gold)
    expected = hashes.get("final_gold")
    if expected and actual != expected:
      raise Pilot120LoaderError("final_gold hash mismatch")
  return gold


def compare_final_vs_pilot_labels(
  final_gold: Iterable[dict[str, Any]],
  pilot_labels: dict[str, dict[str, Any]],
) -> dict[str, Any]:
  """Post-freeze comparison only. Do not use during annotation."""
  unchanged = 0
  changed = 0
  dimensions: dict[str, int] = {}
  cap_ctx_repair_terminal_changes = 0
  details: list[dict[str, Any]] = []
  dims = (
    "terminal_strategy",
    "ambiguity_types",
    "capability_status",
    "capability_interpretation",
    "risk_level",
    "speech_act",
  )
  for record in final_gold:
    rid = record["record_id"]
    pilot = pilot_labels.get(rid)
    if pilot is None:
      continue
    record_changed = False
    changed_dims: list[str] = []
    for dim in dims:
      fv = record.get(dim)
      pv = pilot.get(dim)
      if dim == "ambiguity_types":
        same = set(fv or []) == set(pv or [])
      elif dim == "terminal_strategy":
        pv = pilot.get("terminal_strategy", pilot.get("recommended_strategy"))
        same = fv == pv
      else:
        same = fv == pv
      if not same:
        record_changed = True
        changed_dims.append(dim)
        dimensions[dim] = dimensions.get(dim, 0) + 1
    if record_changed:
      changed += 1
      if pilot.get("capability_context_repaired") is True and "terminal_strategy" in changed_dims:
        cap_ctx_repair_terminal_changes += 1
      details.append({"record_id": rid, "changed_dimensions": changed_dims})
    else:
      unchanged += 1
  return {
    "unchanged": unchanged,
    "changed": changed,
    "changed_dimensions": dimensions,
    "capability_context_repair_terminal_strategy_changes": cap_ctx_repair_terminal_changes,
    "qualitative_stability_note": (
      "Original pilot findings remain qualitatively stable"
      if changed <= max(1, unchanged // 10)
      else "Material label drift vs pilot; inspect changed_dimensions"
    ),
    "details": details,
  }
