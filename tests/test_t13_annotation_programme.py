"""CPU-only tests for T13 annotation programme foundations."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ambiguity_manager.annotation.calibration_data import calibration_candidates
from ambiguity_manager.annotation.canonical import sha256_json
from ambiguity_manager.annotation.contamination import find_source_overlaps
from ambiguity_manager.annotation.coverage import summarise_coverage
from ambiguity_manager.annotation.duplicates import find_duplicates, normalise_text
from ambiguity_manager.annotation.ids import format_record_id, parse_record_id
from ambiguity_manager.annotation.manifests import build_manifest
from ambiguity_manager.annotation.packages import (
  assert_same_record_set,
  build_annotator_package,
  detect_mutation,
  package_bytes_hash,
  read_jsonl,
  strip_hidden_fields,
  write_jsonl,
)
from ambiguity_manager.annotation.roles import (
  RolePolicyError,
  assert_not_author_as_annotator,
  assert_official_annotator_role,
  validate_assignment_payload,
  validate_roles_config,
)
from ambiguity_manager.annotation.schema import (
  ANNOTATION_SCHEMA_VERSION,
  HANDBOOK_VERSION,
  PACKAGE_VERSION,
  load_annotation_schema,
  load_design_cells,
  load_intent_taxonomy,
)
from ambiguity_manager.annotation.validation import (
  empty_cpc,
  validate_annotator_response,
  validate_candidate_record,
  validate_no_gold_fields,
)
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema.v2.taxonomies import AmbiguityType, CapabilityStatus, RiskLevel, RouteLabel


class T13SchemaRoleTests(unittest.TestCase):
  def test_configs_load(self) -> None:
    schema = load_annotation_schema()
    self.assertEqual(schema["schema_version"], "1.0.0")
    self.assertEqual(load_intent_taxonomy()["schema_version"], "1.0.0")
    self.assertEqual(load_design_cells()["main_target_n"], 300)
    self.assertEqual(validate_roles_config(), [])

  def test_valid_candidate(self) -> None:
    record = calibration_candidates()[0]
    self.assertEqual(validate_candidate_record(record), [])

  def test_invalid_intent_and_enums(self) -> None:
    response = self._valid_response()
    response["speech_act"] = "not_a_real_intent"
    self.assertTrue(any("speech_act" in e for e in validate_annotator_response(response)))
    response = self._valid_response()
    response["cpc"]["action"]["status"] = "nope"
    self.assertTrue(any("CPC status" in e for e in validate_annotator_response(response)))
    response = self._valid_response()
    response["ambiguity_types"] = ["not_a_type"]
    self.assertTrue(any("ambiguity type" in e for e in validate_annotator_response(response)))
    response = self._valid_response()
    response["risk_level"] = "extreme"
    self.assertTrue(any("risk_level" in e for e in validate_annotator_response(response)))
    response = self._valid_response()
    response["capability_status"] = "maybe"
    self.assertTrue(any("capability_status" in e for e in validate_annotator_response(response)))
    response = self._valid_response()
    response["recommended_strategy"] = "guess"
    self.assertTrue(any("recommended_strategy" in e for e in validate_annotator_response(response)))

  def test_conditional_fields(self) -> None:
    response = self._valid_response()
    response["recommended_strategy"] = "clarify"
    response["clarification_targets"] = []
    response["clarification_question"] = None
    errors = validate_annotator_response(response)
    self.assertTrue(any("clarification_targets" in e for e in errors))

  def test_role_policy(self) -> None:
    assert_official_annotator_role("ANN-A")
    assert_official_annotator_role("ANN-B")
    with self.assertRaises(RolePolicyError):
      assert_official_annotator_role("AUTHOR-01")
    with self.assertRaises(RolePolicyError):
      assert_not_author_as_annotator("ANN-A", "Mohammed Bangie")
    errors = validate_assignment_payload(
      {"annotator_role": "ANN-A", "person_name": "External Person"}
    )
    self.assertTrue(errors)
    self.assertTrue(validate_no_gold_fields({"gold_route": "execute"}))

  def _valid_response(self) -> dict:
    return {
      "record_id": "manual:2026:syn:0001",
      "speech_act": "directive_command",
      "cpc": empty_cpc("not_applicable"),
      "candidate_interpretations": [],
      "ambiguity_present": False,
      "ambiguity_types": [],
      "compound_ambiguity_count": 0,
      "risk_level": "none",
      "capability_status": "capable",
      "recommended_strategy": "execute",
      "annotator_role": "ANN-A",
      "confidence": "high",
      "timestamp": "2026-07-22T00:00:00Z",
      "handbook_version": HANDBOOK_VERSION,
      "annotation_schema_version": ANNOTATION_SCHEMA_VERSION,
      "package_version": PACKAGE_VERSION,
    }


class T13PackageTests(unittest.TestCase):
  def test_stable_ids_and_hashes(self) -> None:
    self.assertEqual(format_record_id("calibration", 1), "manual:2026:cal:0001")
    self.assertEqual(parse_record_id("manual:2026:cal:0001"), ("calibration", 1, 2026))
    records = calibration_candidates()
    pkg_a1 = build_annotator_package(records, annotator_role="ANN-A", package_id="pkgA")
    pkg_a2 = build_annotator_package(records, annotator_role="ANN-A", package_id="pkgA")
    pkg_b = build_annotator_package(records, annotator_role="ANN-B", package_id="pkgB")
    self.assertEqual(package_bytes_hash(pkg_a1), package_bytes_hash(pkg_a2))
    assert_same_record_set(pkg_a1, pkg_b)
    self.assertNotEqual([r["record_id"] for r in pkg_a1], [r["record_id"] for r in pkg_b])
    for record in pkg_a1:
      self.assertNotIn("hidden", record)
      self.assertNotIn("author_notes", record)
      self.assertFalse(any(k.startswith("gold_") for k in record))
    man1 = build_manifest(
      package_id="pkgA",
      annotator_role="ANN-A",
      partition="calibration",
      records=pkg_a1,
      source_path="x",
    )
    man2 = build_manifest(
      package_id="pkgA",
      annotator_role="ANN-A",
      partition="calibration",
      records=pkg_a2,
      source_path="x",
    )
    self.assertEqual(man1, man2)

  def test_overwrite_refused_and_mutation(self) -> None:
    records = [strip_hidden_fields(calibration_candidates()[0])]
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "p.jsonl"
      digest = write_jsonl(path, records, overwrite=False)
      with self.assertRaises(FileExistsError):
        write_jsonl(path, records, overwrite=False)
      self.assertFalse(detect_mutation(path, digest))
      path.write_text("mutated\n", encoding="utf-8")
      self.assertTrue(detect_mutation(path, digest))


class T13QualityTests(unittest.TestCase):
  def test_duplicates_and_coverage(self) -> None:
    records = calibration_candidates()
    dups = find_duplicates(records)
    self.assertEqual(dups["exact_command"], [])
    self.assertEqual(dups["normalised_command"], [])
    self.assertEqual(normalise_text("Hello,  World!"), "hello world")
    coverage = summarise_coverage(records)
    checks = coverage["calibration_presence_checks"]
    self.assertTrue(all(checks.values()), msg=str(checks))
    overlaps = find_source_overlaps(records)
    # Calibration should generally not collide; allow empty list.
    self.assertIsInstance(overlaps, list)

  def test_calibration_committed_packages(self) -> None:
    root = ProjectPaths.from_repo_root().data_annotations / "t13"
    source = read_jsonl(root / "calibration" / "candidates_source.jsonl")
    self.assertEqual(len(source), 24)
    pkg_a = read_jsonl(root / "assignments" / "ANN-A" / "t13-calibration-ANN-A-v1.jsonl")
    pkg_b = read_jsonl(root / "assignments" / "ANN-B" / "t13-calibration-ANN-B-v1.jsonl")
    assert_same_record_set(pkg_a, pkg_b)
    self.assertEqual(len(pkg_a), 24)
    self.assertNotEqual([r["record_id"] for r in pkg_a], [r["record_id"] for r in pkg_b])
    for package in (pkg_a, pkg_b):
      for record in package:
        self.assertNotIn("hidden", record)
        self.assertFalse(any(str(k).startswith("gold_") for k in record))
    coverage = summarise_coverage(source)
    self.assertTrue(coverage["calibration_presence_checks"]["all_routes"])
    self.assertTrue(coverage["calibration_presence_checks"]["all_ambiguity_types"])
    self.assertTrue(coverage["calibration_presence_checks"]["all_risks"])
    self.assertTrue(coverage["calibration_presence_checks"]["all_capabilities"])
    # partition separation
    self.assertTrue(all(r["dataset_partition"] == "calibration" for r in source))
    for amb in AmbiguityType:
      self.assertGreaterEqual(coverage["counts"]["ambiguity_types"].get(amb.value, 0), 1)
    for risk in RiskLevel:
      self.assertGreaterEqual(coverage["counts"]["risk_level"].get(risk.value, 0), 1)
    for cap in CapabilityStatus:
      self.assertGreaterEqual(coverage["counts"]["capability_status"].get(cap.value, 0), 1)
    for route in RouteLabel:
      self.assertGreaterEqual(coverage["counts"]["recommended_strategy"].get(route.value, 0), 1)

  def test_import_isolation(self) -> None:
    import sys

    import ambiguity_manager.annotation  # noqa: F401

    self.assertNotIn("torch", sys.modules)
    self.assertNotIn("transformers", sys.modules)
    self.assertNotIn("vllm", sys.modules)

  def test_hash_determinism(self) -> None:
    payload = {"a": 1, "b": [2, 3]}
    self.assertEqual(sha256_json(payload), sha256_json({"b": [2, 3], "a": 1}))


if __name__ == "__main__":
  unittest.main()
