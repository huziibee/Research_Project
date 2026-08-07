"""Compound ambiguity / final-protocol v7 QA gates for Pilot-120.

These tests encode freeze contracts. They must not invent official gold.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ambiguity_manager.annotation.final_protocol_v7 import (
  PILOT_120_N,
  PROTOCOL_ID,
  assert_blind_package,
  assert_immutable_evidence_unchanged,
  build_blind_packages,
  capability_class_distribution,
  classify_capability_evidence,
  compute_final_protocol_agreement,
  one_path_determinacy,
  strip_to_permitted_evidence,
  validate_pilot_120_source_subset,
)
from ambiguity_manager.evaluation.pilot_120 import (
  Pilot120LoaderError,
  compare_final_vs_pilot_labels,
  current_freeze_blockers,
  discover_prerequisite_artifacts,
  freeze_pilot_120_v1,
  load_pilot_120_for_evaluation,
  prepare_blind_packages_from_source,
  run_agreement_and_queue,
  write_blocked_status,
)
from ambiguity_manager.annotation.final_protocol_v7 import write_jsonl
from ambiguity_manager.paths import ProjectPaths
from tests.fixtures.pilot_120_synthetic import build_synthetic_pilot_120_tree


def _repo() -> Path:
  return ProjectPaths.from_repo_root().root


def test_prerequisite_docs_now_exist() -> None:
  root = _repo()
  assert (root / "FINAL_SEMANTIC_QA_REPORT.md").is_file()
  assert (root / "docs" / "DEFERRED_FULL_1000_SEMANTIC_QA_NOTES.md").is_file()
  assert (root / "annotations" / "manual_kappa_v7_final_protocol" / "README.md").is_file()
  assert (root / "configs" / "annotation" / "final_protocol_v7.json").is_file()


def test_discovery_and_blocked_status() -> None:
  discovery = discover_prerequisite_artifacts()
  assert "assumed_artifacts" in discovery
  status = write_blocked_status()
  assert status["frozen"] is False
  assert status["full_1000"] == "NOT READY TO FREEZE"
  assert "NOT FROZEN" in status["pilot_120_v1"]
  blockers = current_freeze_blockers()
  assert any("source_canonical" in b for b in blockers)


def test_blind_package_strips_pilot_and_private_labels() -> None:
  dirty = {
    "record_id": "pilot120:demo:0001",
    "command": "Bring me that cup carefully",
    "scene_context": "Kitchen counter with two cups",
    "dialogue_history": [],
    "capability_context": "Robot can grasp mugs under 400g; cannot pour boiling liquid.",
    "pilot_annotator_a_labels": {"terminal_strategy": "execute"},
    "pilot_gold_labels": {"terminal_strategy": "clarify"},
    "private_owner_qa_labels": {"notes": "secret"},
    "prior_adjudication_decisions": {"terminal_strategy": "clarify"},
    "gold_route": "clarify",
    "ANN-A": {"x": 1},
  }
  view = strip_to_permitted_evidence(dirty)
  assert "pilot_annotator_a_labels" not in view
  assert "pilot_gold_labels" not in view
  assert "private_owner_qa_labels" not in view
  assert "prior_adjudication_decisions" not in view
  assert "gold_route" not in view
  assert "ANN-A" not in view
  assert view["command"] == dirty["command"]
  assert view["blind_view"] is True
  package_a, package_b = build_blind_packages([dirty])
  assert_blind_package(package_a)
  assert_blind_package(package_b)
  assert package_a[0]["record_id"] == package_b[0]["record_id"]


def test_capability_class_d_and_one_path_helpers() -> None:
  assert classify_capability_evidence({"capability_context": None}) == "D"
  assert classify_capability_evidence({"capability_context": "tbd"}) == "D"
  good = {
    "capability_context": (
      "Robot arm can reach shelf A; gripper payload 1kg; navigation permitted in kitchen only."
    )
  }
  assert classify_capability_evidence(good) in {"A", "B"}
  assert one_path_determinacy({}, {"terminal_strategy": "clarify"}) is True
  assert (
    one_path_determinacy(
      {"alternate_terminal_strategies": ["execute", "clarify"]},
      {"terminal_strategy": "clarify"},
    )
    is False
  )


def test_immutable_evidence_guard_for_capability_context_only_repairs() -> None:
  before = {
    "record_id": "x",
    "command": "Move the fragile vase",
    "scene_context": "Lab bench",
    "dialogue_history": ["Which vase?"],
    "capability_context": "old",
    "replacement": None,
  }
  after_ok = dict(before)
  after_ok["capability_context"] = "Robot cannot handle fragile glass without padding."
  assert assert_immutable_evidence_unchanged(before, after_ok) == []
  after_bad = dict(after_ok)
  after_bad["command"] = "changed"
  errs = assert_immutable_evidence_unchanged(before, after_bad)
  assert any("command" in e for e in errs)


def test_agreement_metrics_and_pilot_label_namespacing() -> None:
  a = {
    "r1": {
      "record_id": "r1",
      "terminal_strategy": "clarify",
      "recommended_strategy": "clarify",
      "ambiguity_types": ["referential", "spatial"],
      "capability_status": "capable",
      "capability_interpretation": "within_payload",
      "speech_act": "directive_command",
      "risk_level": "low",
      "ambiguity_present": True,
      "confidence": "high",
      "cpc": {},
    },
    "r2": {
      "record_id": "r2",
      "terminal_strategy": "execute",
      "recommended_strategy": "execute",
      "ambiguity_types": ["pragmatic"],
      "capability_status": "conditional",
      "capability_interpretation": "needs_confirmation",
      "speech_act": "indirect_request",
      "risk_level": "medium",
      "ambiguity_present": True,
      "confidence": "medium",
      "cpc": {},
    },
  }
  b = {
    "r1": dict(a["r1"], terminal_strategy="execute", recommended_strategy="execute"),
    "r2": dict(a["r2"]),
  }
  report = compute_final_protocol_agreement(a, b)
  assert report["protocol_id"] == PROTOCOL_ID
  assert report["pilot_annotation_agreement"]["label"] == "pilot_annotation_agreement"
  assert report["terminal_strategy"]["disagreement_count"] == 1
  assert 0.0 <= report["terminal_strategy"]["raw_agreement"] <= 1.0
  assert report["ambiguity_types"]["exact_set_agreement"] == 1.0


def test_repo_pilot_120_not_frozen_and_loader_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
  # Loader must refuse training purpose even against empty/missing freeze
  with pytest.raises(Pilot120LoaderError):
    load_pilot_120_for_evaluation(purpose="training")
  with pytest.raises(Pilot120LoaderError):
    load_pilot_120_for_evaluation(purpose="evaluation")  # not frozen in repo


def test_synthetic_freeze_pipeline_unique_ids_hashes_and_loader(tmp_path: Path) -> None:
  root = build_synthetic_pilot_120_tree(tmp_path)
  sources = [
    json.loads(line)
    for line in (root / "data/annotations/pilot_120_v1/source_canonical.jsonl").read_text().splitlines()
    if line.strip()
  ]
  assert len(sources) == 120
  assert len({r["record_id"] for r in sources}) == 120
  assert capability_class_distribution(sources).get("D", 0) == 0
  assert validate_pilot_120_source_subset(sources) == []

  prep = prepare_blind_packages_from_source(root=root)
  assert prep["n"] == 120

  agreement = run_agreement_and_queue(root=root)
  assert agreement["disagreement_count"] == 3

  # Resolve disagreements
  disag_path = root / "data/annotations/pilot_120_v1/adjudication/disagreements.jsonl"
  decisions = []
  a_by = {
    r["record_id"]: r
    for r in [
      json.loads(line)
      for line in (root / "data/annotations/pilot_120_v1/annotations_raw/ANN-A.jsonl").read_text().splitlines()
      if line.strip()
    ]
  }
  b_by = {
    r["record_id"]: r
    for r in [
      json.loads(line)
      for line in (root / "data/annotations/pilot_120_v1/annotations_raw/ANN-B.jsonl").read_text().splitlines()
      if line.strip()
    ]
  }
  for line in disag_path.read_text().splitlines():
    item = json.loads(line)
    rid = item["record_id"]
    decisions.append(
      {
        "record_id": rid,
        "status": "resolved",
        "adjudicator_role": "SYN-ADJ",
        "adjudication_decision": {
          "speech_act": a_by[rid]["speech_act"],
          "terminal_strategy": "clarify",
          "recommended_strategy": "clarify",
          "ambiguity_types": a_by[rid]["ambiguity_types"],
          "capability_status": a_by[rid]["capability_status"],
          "capability_interpretation": a_by[rid]["capability_interpretation"],
          "risk_level": a_by[rid]["risk_level"],
        },
        "rationale": "synthetic adjudication for pipeline test",
        "ANN-A_original": a_by[rid],
        "ANN-B_original": b_by[rid],
        "retains_originals": True,
      }
    )
  write_jsonl(root / "data/annotations/pilot_120_v1/adjudication/decisions.jsonl", decisions)

  report = freeze_pilot_120_v1(root=root)
  assert report["status"] == "FROZEN"
  assert report["n_records"] == 120
  assert report["capability_class_distribution"]["D"] == 0
  assert report["one_path_determinacy"]["true_count"] == 120
  hashes = report["sha256"]
  assert "final_gold" in hashes and len(hashes["final_gold"]) == 64
  assert "manifest" in hashes and len(hashes["manifest"]) == 64

  # Stable hash recompute
  gold_path = root / "data/annotations/pilot_120_v1/final_gold.jsonl"
  from ambiguity_manager.annotation.final_protocol_v7 import file_sha256

  assert file_sha256(gold_path) == hashes["final_gold"]

  gold = load_pilot_120_for_evaluation(root=root, purpose="evaluation")
  assert len(gold) == 120
  with pytest.raises(Pilot120LoaderError):
    load_pilot_120_for_evaluation(root=root, purpose="train")

  # Post-freeze pilot comparison helper
  pilot = {
    rid: {
      "terminal_strategy": a_by[rid]["terminal_strategy"],
      "ambiguity_types": a_by[rid]["ambiguity_types"],
      "capability_status": a_by[rid]["capability_status"],
      "capability_interpretation": a_by[rid]["capability_interpretation"],
      "risk_level": a_by[rid]["risk_level"],
      "speech_act": a_by[rid]["speech_act"],
      "capability_context_repaired": rid.endswith("0002"),
    }
    for rid in a_by
  }
  cmp = compare_final_vs_pilot_labels(gold, pilot)
  assert cmp["unchanged"] + cmp["changed"] == 120


def test_full_1000_remains_deferred_in_docs() -> None:
  text = (_repo() / "docs" / "DEFERRED_FULL_1000_SEMANTIC_QA_NOTES.md").read_text(encoding="utf-8")
  assert "NOT READY TO FREEZE" in text
  report = (_repo() / "FINAL_SEMANTIC_QA_REPORT.md").read_text(encoding="utf-8")
  assert "NOT FROZEN" in report
  assert "NOT READY TO FREEZE" in report
