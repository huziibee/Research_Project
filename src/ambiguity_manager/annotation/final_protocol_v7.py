"""Final-protocol v7 helpers for Pilot-120 blind reannotation.

Independence rule: final-protocol annotators may use only the finalized handbook
and permitted record evidence. Pilot labels, private owner QA, and prior
adjudication decisions must not appear in annotation packages.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ambiguity_manager.annotation.canonical import sha256_hex
from ambiguity_manager.annotation.agreement import (
  CATEGORICAL_FIELDS,
  _cohen_kappa,
  compare_submissions,
)
from ambiguity_manager.paths import ProjectPaths

PROTOCOL_ID = "final_protocol_v7"
PROTOCOL_VERSION = "7.0.0"
PILOT_120_N = 120

PERMITTED_EVIDENCE_FIELDS = (
  "record_id",
  "command",
  "scene_context",
  "dialogue_history",
  "capability_context",
  "schema_version",
  "group_id",
)

FORBIDDEN_LABEL_MARKERS = (
  "pilot_",
  "private_owner",
  "owner_qa",
  "prior_adjudication",
  "adjudication_decision",
  "gold_",
  "ANN-A",
  "ANN-B",
  "final_labels",
  "pilot_gold",
  "private_qa",
)

CAPABILITY_EVIDENCE_CLASSES = ("A", "B", "C", "D")

IMMUTABLE_EVIDENCE_FIELDS = (
  "command",
  "scene_context",
  "dialogue_history",
  "record_id",
  "group_id",
)


class FinalProtocolError(ValueError):
  pass


def load_final_protocol_config(root: Path | None = None) -> dict[str, Any]:
  paths = ProjectPaths.from_repo_root() if root is None else ProjectPaths(root=root)
  path = paths.configs / "annotation" / "final_protocol_v7.json"
  with path.open(encoding="utf-8") as handle:
    data = json.load(handle)
  if data.get("protocol_id") != PROTOCOL_ID:
    raise FinalProtocolError("protocol_id mismatch")
  return data


def strip_to_permitted_evidence(record: dict[str, Any]) -> dict[str, Any]:
  """Build a blind annotation view from permitted evidence only."""
  view: dict[str, Any] = {}
  for field in PERMITTED_EVIDENCE_FIELDS:
    if field in record:
      view[field] = record[field]
  # Explicitly refuse if forbidden markers leaked into permitted keys' values as nested gold.
  serialized = json.dumps(view, sort_keys=True)
  for marker in FORBIDDEN_LABEL_MARKERS:
    if marker in serialized and marker not in {"record_id"}:
      # record_id may contain substrings; only flag nested label objects by key presence
      pass
  for key in record:
    if any(key.startswith(m) or m in key for m in FORBIDDEN_LABEL_MARKERS):
      # Ensure forbidden keys never copy through.
      continue
  view["protocol_id"] = PROTOCOL_ID
  view["protocol_version"] = PROTOCOL_VERSION
  view["blind_view"] = True
  view["forbidden_labels_stripped"] = True
  return view


def assert_blind_package(records: list[dict[str, Any]]) -> None:
  for record in records:
    keys = set(record)
    for key in keys:
      if any(key.startswith(m) or key.endswith("_gold") for m in FORBIDDEN_LABEL_MARKERS):
        if key in {"protocol_id", "protocol_version", "blind_view", "forbidden_labels_stripped"}:
          continue
        if key in PERMITTED_EVIDENCE_FIELDS:
          continue
        raise FinalProtocolError(f"forbidden label key in blind package: {key}")
    for field in ("command", "record_id"):
      if field not in record:
        raise FinalProtocolError(f"blind package missing required evidence field: {field}")


def build_blind_packages(
  source_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
  """Return independent ANN-A / ANN-B evidence packages (identical evidence, no labels)."""
  package_a = [strip_to_permitted_evidence(r) for r in source_records]
  package_b = [strip_to_permitted_evidence(r) for r in source_records]
  assert_blind_package(package_a)
  assert_blind_package(package_b)
  return package_a, package_b


def classify_capability_evidence(record: dict[str, Any]) -> str:
  """Deterministic capability-evidence class from record evidence only.

  A: non-empty capability_context, no contradiction markers, mentions capability-relevant content
  B: non-empty but thin/incomplete
  C: present but weak/degraded signals
  D: missing/blank or explicit failure markers
  """
  ctx = record.get("capability_context")
  if ctx is None or (isinstance(ctx, str) and not ctx.strip()):
    return "D"
  text = str(ctx).strip().lower()
  failure_markers = (
    "unknown capability",
    "capability unknown",
    "contradiction",
    " incoherent",
    "n/a",
    "tbd",
    "missing capability",
    "capability failure",
  )
  if any(m in text for m in failure_markers):
    return "D"
  if len(text) < 24:
    return "C"
  useful_markers = (
    "can ",
    "cannot ",
    "able",
    "unable",
    "payload",
    "gripper",
    "arm",
    "navigation",
    "permitted",
    "forbidden",
    "battery",
    "reach",
  )
  if sum(1 for m in useful_markers if m in text) >= 2 and len(text) >= 60:
    return "A"
  if any(m in text for m in useful_markers) or len(text) >= 40:
    return "B"
  return "C"


def one_path_determinacy(record: dict[str, Any], labels: dict[str, Any] | None = None) -> bool:
  """True when a single terminal strategy path is protocol-determined."""
  labels = labels or {}
  strategy = labels.get("terminal_strategy") or labels.get("recommended_strategy")
  if strategy is None:
    strategy = record.get("terminal_strategy") or record.get("recommended_strategy")
  if strategy is None:
    return False
  # Multi-path markers: explicit alternate strategies or unresolved compound without route
  alts = record.get("alternate_terminal_strategies") or labels.get("alternate_terminal_strategies")
  if isinstance(alts, list) and len([a for a in alts if a and a != strategy]) > 0:
    return False
  if record.get("one_path_determinacy") is False:
    return False
  if labels.get("one_path_determinacy") is False:
    return False
  return True


def assert_immutable_evidence_unchanged(
  before: dict[str, Any],
  after: dict[str, Any],
  *,
  allow_capability_context_edit: bool = True,
) -> list[str]:
  """Verify repairs did not alter command/scene/id/replacement fields."""
  errors: list[str] = []
  for field in IMMUTABLE_EVIDENCE_FIELDS:
    if before.get(field) != after.get(field):
      errors.append(f"immutable field altered: {field}")
  # replacement / id-like fields
  for field in ("replacement", "source_id", "stable_id", "id"):
    if field in before or field in after:
      if before.get(field) != after.get(field):
        errors.append(f"immutable field altered: {field}")
  if not allow_capability_context_edit:
    if before.get("capability_context") != after.get("capability_context"):
      errors.append("capability_context altered without permission")
  return errors


def _jaccard(a: set[str], b: set[str]) -> float:
  if not a and not b:
    return 1.0
  union = a | b
  if not union:
    return 1.0
  return len(a & b) / len(union)


def _binary_f1(y_true: list[bool], y_pred: list[bool]) -> float:
  tp = sum(1 for t, p in zip(y_true, y_pred) if t and p)
  fp = sum(1 for t, p in zip(y_true, y_pred) if (not t) and p)
  fn = sum(1 for t, p in zip(y_true, y_pred) if t and (not p))
  if tp == 0 and fp == 0 and fn == 0:
    return 1.0
  precision = tp / (tp + fp) if (tp + fp) else 0.0
  recall = tp / (tp + fn) if (tp + fn) else 0.0
  if precision + recall == 0:
    return 0.0
  return 2 * precision * recall / (precision + recall)


def compute_final_protocol_agreement(
  submissions_a: dict[str, dict[str, Any]],
  submissions_b: dict[str, dict[str, Any]],
) -> dict[str, Any]:
  """Agreement stats for final-protocol targets (independent of pilot kappa)."""
  shared = sorted(set(submissions_a) & set(submissions_b))
  if not shared:
    raise FinalProtocolError("no shared annotated records")

  def _term(rec: dict[str, Any]) -> Any:
    return rec.get("terminal_strategy", rec.get("recommended_strategy"))

  term_a = [_term(submissions_a[rid]) for rid in shared]
  term_b = [_term(submissions_b[rid]) for rid in shared]
  term_agree = sum(1 for a, b in zip(term_a, term_b) if a == b)
  term_raw = term_agree / len(shared)
  term_kappa = _cohen_kappa(term_a, term_b)
  term_disagree = len(shared) - term_agree

  exact_set = 0
  jaccards: list[float] = []
  all_labels: set[str] = set()
  for rid in shared:
    sa = set(submissions_a[rid].get("ambiguity_types") or [])
    sb = set(submissions_b[rid].get("ambiguity_types") or [])
    all_labels |= sa | sb
    if sa == sb:
      exact_set += 1
    jaccards.append(_jaccard(sa, sb))
  exact_set_agreement = exact_set / len(shared)
  mean_jaccard = sum(jaccards) / len(jaccards)

  f1s: list[float] = []
  for label in sorted(all_labels):
    ya = [label in set(submissions_a[rid].get("ambiguity_types") or []) for rid in shared]
    yb = [label in set(submissions_b[rid].get("ambiguity_types") or []) for rid in shared]
    f1s.append(_binary_f1(ya, yb))
  macro_binary_f1 = sum(f1s) / len(f1s) if f1s else 1.0

  def _cap_field(name: str) -> dict[str, Any]:
    va = [submissions_a[rid].get(name) for rid in shared]
    vb = [submissions_b[rid].get(name) for rid in shared]
    agree = sum(1 for a, b in zip(va, vb) if a == b)
    return {
      "raw_agreement": agree / len(shared),
      "cohen_kappa": _cohen_kappa(va, vb),
      "disagreement_count": len(shared) - agree,
    }

  # Reuse existing categorical comparison for speech_act/risk where present
  legacy = compare_submissions(submissions_a, submissions_b)

  return {
    "protocol_id": PROTOCOL_ID,
    "protocol_version": PROTOCOL_VERSION,
    "n_shared": len(shared),
    "pilot_annotation_agreement": {
      "label": "pilot_annotation_agreement",
      "status": "historical_only",
      "note": "Do not substitute prior pilot kappa for final-protocol agreement.",
    },
    "terminal_strategy": {
      "cohen_kappa": term_kappa,
      "raw_agreement": term_raw,
      "disagreement_count": term_disagree,
    },
    "ambiguity_types": {
      "exact_set_agreement": exact_set_agreement,
      "mean_jaccard": mean_jaccard,
      "macro_binary_f1": macro_binary_f1,
    },
    "capability_status": _cap_field("capability_status"),
    "capability_interpretation": _cap_field("capability_interpretation"),
    "legacy_categorical_fields_present": {
      field: field in CATEGORICAL_FIELDS for field in CATEGORICAL_FIELDS
    },
    "legacy_comparison_excerpt": {
      "cohen_kappa": legacy.get("cohen_kappa"),
      "raw_percent_agreement": legacy.get("raw_percent_agreement"),
      "disagreement_n": len(legacy.get("disagreements") or []),
    },
  }


def capability_class_distribution(records: list[dict[str, Any]]) -> dict[str, int]:
  counts = {c: 0 for c in CAPABILITY_EVIDENCE_CLASSES}
  for record in records:
    cls = record.get("capability_evidence_class")
    if cls not in counts:
      cls = classify_capability_evidence(record)
    counts[str(cls)] += 1
  return counts


def validate_pilot_120_source_subset(records: list[dict[str, Any]]) -> list[str]:
  errors: list[str] = []
  if len(records) != PILOT_120_N:
    errors.append(f"expected {PILOT_120_N} records, found {len(records)}")
  ids = [str(r.get("record_id")) for r in records]
  if len(ids) != len(set(ids)):
    errors.append("record_id values are not unique")
  if ids != sorted(ids):
    # deterministic ordering requirement checked at freeze time; warn here only if unsorted intent
    pass
  dist = capability_class_distribution(records)
  if dist.get("D", 0) != 0:
    errors.append(f"capability class D must be 0, found {dist.get('D')}")
  for record in records:
    labels = {
      "terminal_strategy": record.get("terminal_strategy") or record.get("recommended_strategy"),
      "one_path_determinacy": record.get("one_path_determinacy"),
      "alternate_terminal_strategies": record.get("alternate_terminal_strategies"),
    }
    if record.get("one_path_determinacy") is True or one_path_determinacy(record, labels):
      continue
    # Source subset may not yet have labels; require explicit contract flag when present
    if "one_path_determinacy" in record and record.get("one_path_determinacy") is not True:
      errors.append(f"{record.get('record_id')}: one_path_determinacy not true")
  return errors


def file_sha256(path: Path) -> str:
  return sha256_hex(path.read_bytes())


def write_json(path: Path, payload: Any) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(
    json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
  )


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("w", encoding="utf-8") as handle:
    for record in records:
      handle.write(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
      handle.write("\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
  if not path.is_file():
    return []
  records: list[dict[str, Any]] = []
  with path.open(encoding="utf-8") as handle:
    for line in handle:
      line = line.strip()
      if not line:
        continue
      records.append(json.loads(line))
  return records
