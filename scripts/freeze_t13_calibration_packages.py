#!/usr/bin/env python3
"""Freeze T13 calibration packages into data/annotations/t13/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from ambiguity_manager.annotation.calibration_data import calibration_candidates
from ambiguity_manager.annotation.manifests import build_manifest, write_manifest
from ambiguity_manager.annotation.packages import (
  assert_same_record_set,
  build_annotator_package,
  write_jsonl,
)
from ambiguity_manager.annotation.reports import build_quality_report, write_json_report
from ambiguity_manager.annotation.validation import validate_candidate_record
from ambiguity_manager.paths import ProjectPaths


def main() -> int:
  paths = ProjectPaths.from_repo_root(Path(__file__))
  root = paths.data_annotations / "t13"
  cal_dir = root / "calibration"
  assign_a = root / "assignments" / "ANN-A"
  assign_b = root / "assignments" / "ANN-B"
  manifests = root / "manifests"
  reports = root / "reports"
  main_ready = root / "main_pool_ readiness".replace(" ", "_")  # typo guard
  main_ready = root / "main_pool_readiness"

  records = calibration_candidates()
  for record in records:
    errors = validate_candidate_record(record, require_hidden=True)
    if errors:
      print(record["record_id"], errors, file=sys.stderr)
      return 1

  source_path = cal_dir / "candidates_source.jsonl"
  package_a_id = "t13-calibration-ANN-A-v1"
  package_b_id = "t13-calibration-ANN-B-v1"
  pkg_a = build_annotator_package(records, annotator_role="ANN-A", package_id=package_a_id)
  pkg_b = build_annotator_package(records, annotator_role="ANN-B", package_id=package_b_id)
  assert_same_record_set(pkg_a, pkg_b)

  write_jsonl(source_path, records, overwrite=True)
  write_jsonl(assign_a / f"{package_a_id}.jsonl", pkg_a, overwrite=True)
  write_jsonl(assign_b / f"{package_b_id}.jsonl", pkg_b, overwrite=True)

  man_source = build_manifest(
    package_id="t13-calibration-source-v1",
    annotator_role=None,
    partition="calibration",
    records=records,
    source_path=str(source_path.relative_to(paths.root).as_posix()),
    extra={"contains_hidden_author_fields": True, "official_annotator_package": False},
  )
  man_a = build_manifest(
    package_id=package_a_id,
    annotator_role="ANN-A",
    partition="calibration",
    records=pkg_a,
    source_path=str(source_path.relative_to(paths.root).as_posix()),
    extra={"contains_hidden_author_fields": False, "official_annotator_package": True},
  )
  man_b = build_manifest(
    package_id=package_b_id,
    annotator_role="ANN-B",
    partition="calibration",
    records=pkg_b,
    source_path=str(source_path.relative_to(paths.root).as_posix()),
    extra={"contains_hidden_author_fields": False, "official_annotator_package": True},
  )
  write_manifest(manifests / "t13-calibration-source-v1.json", man_source, overwrite=True)
  write_manifest(manifests / f"{package_a_id}.json", man_a, overwrite=True)
  write_manifest(manifests / f"{package_b_id}.json", man_b, overwrite=True)

  quality = build_quality_report(records, root=paths.root)
  write_json_report(reports / "calibration_quality.json", quality, overwrite=True)
  write_json_report(
    reports / "calibration_package_hashes.json",
    {
      "source_sha256": man_source["package_sha256"],
      "ann_a_sha256": man_a["package_sha256"],
      "ann_b_sha256": man_b["package_sha256"],
      "record_ids": man_a["record_ids"],
      "order_a": man_a["record_order"],
      "order_b": man_b["record_order"],
    },
    overwrite=True,
  )

  # Main-pool readiness templates (no 300 freeze).
  main_ready.mkdir(parents=True, exist_ok=True)
  template = {
    "record_id": "manual:2026:main:0000",
    "command": "<human-authored command>",
    "dialogue_history": [],
    "scene_context": "<scene or null>",
    "capability_context": "<capability or null>",
    "visible_provenance_category": "human_seed",
    "package_version": "1.0.0",
    "handbook_version": "1.0.0",
    "annotation_schema_version": "1.0.0",
    "dataset_partition": "main",
    "hidden": {
      "design_cell": {
        "ambiguity_profile": "<clear_no_ambiguity|single_ambiguity|compound_two_types|compound_three_or_more>",
        "ambiguity_types": [],
        "compound_ambiguity_count": 0,
        "risk_level": "none",
        "capability_status": "capable",
        "recommended_strategy": "execute",
        "speech_act": "directive_command",
        "speech_act_proxy": "direct",
        "context_proxy": "context_rich",
        "safety_sensitive": False,
      },
      "seed_id": "main-seed-000",
      "template_id": "main-template-000",
      "group_id": "main-group-000",
      "author_notes": "",
      "review_codes": [],
      "intended_answer": None,
      "model_output": None,
      "model_critique": None,
      "author_expectation": None,
    },
  }
  (main_ready / "main_candidate_template.json").write_text(
    json.dumps(template, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
  )
  reserve = dict(template)
  reserve["record_id"] = "manual:2026:rsv:0000"
  reserve["dataset_partition"] = "reserve"
  (main_ready / "reserve_candidate_template.json").write_text(
    json.dumps(reserve, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
  )
  checklist = {
    "review_checklist": [
      "naturalness",
      "robot_interaction_realism",
      "sufficient_context",
      "no_answer_leakage",
      "no_unintended_contradiction",
      "no_duplicate_semantic_frame",
      "risk_metadata_correct",
      "traceable_provenance",
      "design_cell_assigned",
      "schema_valid",
    ],
    "quarantine_workflow": [
      "mark review_codes with quarantine reason",
      "move to reserve or exclude report",
      "do not include in ANN packages until fixed",
    ],
  }
  (main_ready / "review_checklist.json").write_text(
    json.dumps(checklist, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
  )
  remaining = {
    "main_target_n": 300,
    "authored_main_n": 0,
    "calibration_n": 24,
    "calibration_enters_main_gold_automatically": False,
    "remaining_to_author": 300,
    "authoring_queue_note": "Fill design-cell deficits from configs/annotation/design_cells_v1.json using coverage CLI.",
  }
  (main_ready / "remaining_count_report.json").write_text(
    json.dumps(remaining, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
  )
  print(json.dumps({"ok": True, "n": len(records), "source": str(source_path)}, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
