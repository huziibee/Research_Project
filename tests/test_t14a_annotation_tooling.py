"""CPU-only tests for T14A blind annotation tooling foundations."""

from __future__ import annotations

import unittest
from copy import deepcopy

from ambiguity_manager.annotation.agreement import (
  AnnotationToolingError,
  GoldExportGate,
  build_adjudication_queue,
  compare_submissions,
  export_synthetic_gold,
  progress,
  validate_gold_export_gate,
)
from ambiguity_manager.annotation.schema import (
  ANNOTATION_SCHEMA_VERSION,
  HANDBOOK_VERSION,
  PACKAGE_VERSION,
)
from ambiguity_manager.annotation.validation import empty_cpc


def _submission(record_id: str, role: str, **overrides):
  base = {
    "record_id": record_id,
    "speech_act": "directive_command",
    "cpc": empty_cpc("not_applicable"),
    "candidate_interpretations": [],
    "ambiguity_present": False,
    "ambiguity_types": [],
    "compound_ambiguity_count": 0,
    "risk_level": "none",
    "capability_status": "capable",
    "recommended_strategy": "execute",
    "annotator_role": role,
    "confidence": "high",
    "timestamp": "2026-07-22T00:00:00Z",
    "handbook_version": HANDBOOK_VERSION,
    "annotation_schema_version": ANNOTATION_SCHEMA_VERSION,
    "package_version": PACKAGE_VERSION,
    "dataset_partition": "synthetic_test",
  }
  base.update(overrides)
  return base


class T14AAgreementTests(unittest.TestCase):
  def test_perfect_agreement(self) -> None:
    a = {
      "manual:2026:syn:0001": _submission("manual:2026:syn:0001", "ANN-A"),
      "manual:2026:syn:0002": _submission("manual:2026:syn:0002", "ANN-A"),
    }
    b = {
      "manual:2026:syn:0001": _submission("manual:2026:syn:0001", "ANN-B"),
      "manual:2026:syn:0002": _submission("manual:2026:syn:0002", "ANN-B"),
    }
    comparison = compare_submissions(a, b)
    self.assertEqual(comparison["n_shared"], 2)
    self.assertEqual(comparison["disagreements"], [])
    self.assertEqual(comparison["raw_percent_agreement"]["speech_act"], 1.0)
    self.assertEqual(comparison["cohen_kappa"]["speech_act"], 1.0)
    self.assertEqual(comparison["mean_ambiguity_jaccard"], 1.0)
    self.assertEqual(comparison["mean_cpc_slot_agreement"], 1.0)
    self.assertEqual(build_adjudication_queue(comparison), [])

  def test_categorical_and_ambiguity_disagreement(self) -> None:
    a = {
      "manual:2026:syn:0001": _submission(
        "manual:2026:syn:0001",
        "ANN-A",
        recommended_strategy="clarify",
        clarification_targets=["object"],
        clarification_question="Which object?",
        ambiguity_present=True,
        ambiguity_types=["referential"],
        compound_ambiguity_count=1,
      )
    }
    b = {
      "manual:2026:syn:0001": _submission(
        "manual:2026:syn:0001",
        "ANN-B",
        recommended_strategy="execute",
        ambiguity_present=True,
        ambiguity_types=["referential", "spatial"],
        compound_ambiguity_count=2,
      )
    }
    comparison = compare_submissions(a, b)
    self.assertEqual(len(comparison["disagreements"]), 1)
    self.assertLess(comparison["mean_ambiguity_jaccard"], 1.0)
    queue = build_adjudication_queue(comparison)
    self.assertEqual(queue[0]["status"], "unresolved")

  def test_cpc_slot_agreement(self) -> None:
    cpc_a = empty_cpc("not_applicable")
    cpc_b = empty_cpc("not_applicable")
    cpc_a["object"] = {"value": "cup", "status": "filled"}
    cpc_b["object"] = {"value": "mug", "status": "filled"}
    a = {"manual:2026:syn:0001": _submission("manual:2026:syn:0001", "ANN-A", cpc=cpc_a)}
    b = {"manual:2026:syn:0001": _submission("manual:2026:syn:0001", "ANN-B", cpc=cpc_b)}
    comparison = compare_submissions(a, b)
    self.assertLess(comparison["mean_cpc_slot_agreement"], 1.0)

  def test_progress_and_missing(self) -> None:
    prog = progress(
      ["manual:2026:syn:0001", "manual:2026:syn:0002"],
      {"manual:2026:syn:0001": _submission("manual:2026:syn:0001", "ANN-A")},
    )
    self.assertEqual(prog["n_complete"], 1)
    self.assertEqual(prog["missing_ids"], ["manual:2026:syn:0002"])

  def test_gold_export_gates(self) -> None:
    a = {"manual:2026:syn:0001": _submission("manual:2026:syn:0001", "ANN-A")}
    b = {
      "manual:2026:syn:0001": _submission(
        "manual:2026:syn:0001",
        "ANN-B",
        recommended_strategy="clarify",
        clarification_targets=["object"],
        clarification_question="Which?",
      )
    }
    gate = GoldExportGate(
      submissions_a=a,
      submissions_b=b,
      adjudication_records=[],
      package_hash_a="aaa",
      package_hash_b="bbb",
      expected_package_hash_a="aaa",
      expected_package_hash_b="bbb",
    )
    errors = validate_gold_export_gate(gate)
    self.assertTrue(any("unresolved" in e or "missing adjudication" in e for e in errors))
    with self.assertRaises(AnnotationToolingError):
      export_synthetic_gold(gate)

    resolved = {
      "record_id": "manual:2026:syn:0001",
      "status": "resolved",
      "adjudicator_role": "SUP-REVIEW-01",
      "adjudication_decision": {"recommended_strategy": "clarify"},
      "retains_originals": True,
      "ANN-A_original": a["manual:2026:syn:0001"],
      "ANN-B_original": b["manual:2026:syn:0001"],
      "handbook_version": HANDBOOK_VERSION,
      "annotation_schema_version": ANNOTATION_SCHEMA_VERSION,
      "package_version": PACKAGE_VERSION,
    }
    gate.adjudication_records = [resolved]
    gold = export_synthetic_gold(gate)
    self.assertEqual(len(gold), 1)
    self.assertTrue(gold[0]["synthetic"])
    self.assertIn("ANN-A_original_sha256", gold[0])

    # invalid adjudicator AUTHOR-01
    bad = deepcopy(resolved)
    bad["adjudicator_role"] = "AUTHOR-01"
    gate.adjudication_records = [bad]
    self.assertTrue(any("invalid" in e for e in validate_gold_export_gate(gate)))

    # refuse calibration/main export in this task
    a_cal = {
      "manual:2026:cal:0001": _submission(
        "manual:2026:cal:0001",
        "ANN-A",
        dataset_partition="calibration",
      )
    }
    b_cal = {
      "manual:2026:cal:0001": _submission(
        "manual:2026:cal:0001",
        "ANN-B",
        dataset_partition="calibration",
      )
    }
    gate_cal = GoldExportGate(
      submissions_a=a_cal,
      submissions_b=b_cal,
      adjudication_records=[],
      package_hash_a="x",
      package_hash_b="y",
      expected_package_hash_a="x",
      expected_package_hash_b="y",
    )
    with self.assertRaises(AnnotationToolingError):
      export_synthetic_gold(gate_cal)

  def test_package_hash_mismatch_blocks(self) -> None:
    a = {"manual:2026:syn:0001": _submission("manual:2026:syn:0001", "ANN-A")}
    b = {"manual:2026:syn:0001": _submission("manual:2026:syn:0001", "ANN-B")}
    gate = GoldExportGate(
      submissions_a=a,
      submissions_b=b,
      adjudication_records=[],
      package_hash_a="aaa",
      package_hash_b="bbb",
      expected_package_hash_a="zzz",
      expected_package_hash_b="bbb",
    )
    self.assertTrue(any("ANN-A package hash" in e for e in validate_gold_export_gate(gate)))


if __name__ == "__main__":
  unittest.main()
