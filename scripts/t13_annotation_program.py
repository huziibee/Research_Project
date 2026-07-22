#!/usr/bin/env python3
"""T13 annotation programme CLI (CPU-only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from ambiguity_manager.annotation.contamination import find_source_overlaps
from ambiguity_manager.annotation.coverage import summarise_coverage
from ambiguity_manager.annotation.duplicates import find_duplicates
from ambiguity_manager.annotation.manifests import build_manifest, write_manifest
from ambiguity_manager.annotation.packages import (
  assert_same_record_set,
  build_annotator_package,
  package_bytes_hash,
  read_jsonl,
  write_jsonl,
)
from ambiguity_manager.annotation.reports import build_quality_report, write_json_report
from ambiguity_manager.annotation.roles import validate_roles_config
from ambiguity_manager.annotation.schema import (
  ANNOTATION_SCHEMA_VERSION,
  HANDBOOK_VERSION,
  PACKAGE_VERSION,
  clear_config_cache,
  load_annotation_schema,
  load_design_cells,
  load_intent_taxonomy,
  load_roles,
  load_route_precedence,
)
from ambiguity_manager.annotation.validation import (
  validate_annotator_package_record,
  validate_candidate_record,
)
from ambiguity_manager.paths import ProjectPaths


def _repo() -> ProjectPaths:
  return ProjectPaths.from_repo_root(Path(__file__))


def cmd_validate_schema(_: argparse.Namespace) -> int:
  clear_config_cache()
  load_annotation_schema()
  load_roles()
  load_intent_taxonomy()
  load_route_precedence()
  load_design_cells()
  errors = validate_roles_config()
  if errors:
    for err in errors:
      print(err, file=sys.stderr)
    return 1
  print(
    json.dumps(
      {
        "ok": True,
        "handbook_version": HANDBOOK_VERSION,
        "annotation_schema_version": ANNOTATION_SCHEMA_VERSION,
        "package_version": PACKAGE_VERSION,
      },
      sort_keys=True,
    )
  )
  return 0


def cmd_validate_candidates(args: argparse.Namespace) -> int:
  records = read_jsonl(Path(args.path))
  failures = 0
  for record in records:
    errors = validate_candidate_record(record, require_hidden=True)
    if errors:
      failures += 1
      print(f"{record.get('record_id')}: " + "; ".join(errors), file=sys.stderr)
  if failures:
    return 1
  print(json.dumps({"ok": True, "n_records": len(records)}, sort_keys=True))
  return 0


def cmd_duplicates(args: argparse.Namespace) -> int:
  records = read_jsonl(Path(args.path))
  payload = find_duplicates(records)
  out = Path(args.output) if args.output else _repo().outputs / "t13" / "duplicates.json"
  if not args.dry_run:
    write_json_report(out, payload, overwrite=True)
  print(json.dumps({"ok": True, "output": str(out), "summary": {k: len(v) for k, v in payload.items()}}, sort_keys=True))
  return 0


def cmd_contamination(args: argparse.Namespace) -> int:
  records = read_jsonl(Path(args.path))
  overlaps = find_source_overlaps(records, root=_repo().root)
  payload = {"n_overlaps": len(overlaps), "overlaps": overlaps}
  out = Path(args.output) if args.output else _repo().outputs / "t13" / "contamination.json"
  if not args.dry_run:
    write_json_report(out, payload, overwrite=True)
  print(json.dumps({"ok": True, "output": str(out), "n_overlaps": len(overlaps)}, sort_keys=True))
  return 0


def cmd_coverage(args: argparse.Namespace) -> int:
  records = read_jsonl(Path(args.path))
  payload = summarise_coverage(records)
  out = Path(args.output) if args.output else _repo().outputs / "t13" / "coverage.json"
  if not args.dry_run:
    write_json_report(out, payload, overwrite=True)
  print(json.dumps({"ok": True, "output": str(out), "n_records": payload["n_records"]}, sort_keys=True))
  return 0


def cmd_build_packages(args: argparse.Namespace) -> int:
  source = Path(args.path)
  records = read_jsonl(source)
  for record in records:
    errors = validate_candidate_record(record, require_hidden=True)
    if errors:
      print(f"{record.get('record_id')}: " + "; ".join(errors), file=sys.stderr)
      return 1
  out_root = Path(args.output) if args.output else _repo().outputs / "t13" / "packages"
  package_a_id = args.package_a_id or "t13-cal-ANN-A-v1"
  package_b_id = args.package_b_id or "t13-cal-ANN-B-v1"
  pkg_a = build_annotator_package(records, annotator_role="ANN-A", package_id=package_a_id)
  pkg_b = build_annotator_package(records, annotator_role="ANN-B", package_id=package_b_id)
  assert_same_record_set(pkg_a, pkg_b)
  if args.dry_run:
    print(
      json.dumps(
        {
          "ok": True,
          "dry_run": True,
          "n_records": len(records),
          "hash_a": package_bytes_hash(pkg_a),
          "hash_b": package_bytes_hash(pkg_b),
        },
        sort_keys=True,
      )
    )
    return 0
  path_a = out_root / "ANN-A" / f"{package_a_id}.jsonl"
  path_b = out_root / "ANN-B" / f"{package_b_id}.jsonl"
  overwrite = bool(args.overwrite)
  hash_a = write_jsonl(path_a, pkg_a, overwrite=overwrite)
  hash_b = write_jsonl(path_b, pkg_b, overwrite=overwrite)
  man_a = build_manifest(
    package_id=package_a_id,
    annotator_role="ANN-A",
    partition=str(records[0].get("dataset_partition", "calibration")),
    records=pkg_a,
    source_path=str(source.as_posix()),
  )
  man_b = build_manifest(
    package_id=package_b_id,
    annotator_role="ANN-B",
    partition=str(records[0].get("dataset_partition", "calibration")),
    records=pkg_b,
    source_path=str(source.as_posix()),
  )
  write_manifest(out_root / "manifests" / f"{package_a_id}.json", man_a, overwrite=overwrite)
  write_manifest(out_root / "manifests" / f"{package_b_id}.json", man_b, overwrite=overwrite)
  quality = build_quality_report(records, root=_repo().root)
  write_json_report(out_root / "reports" / "quality.json", quality, overwrite=True)
  print(
    json.dumps(
      {
        "ok": True,
        "path_a": str(path_a),
        "path_b": str(path_b),
        "hash_a": hash_a,
        "hash_b": hash_b,
      },
      sort_keys=True,
    )
  )
  return 0


def cmd_verify_package(args: argparse.Namespace) -> int:
  path = Path(args.path)
  records = read_jsonl(path)
  errors: list[str] = []
  for record in records:
    if "hidden" in record or any(k in record for k in ("intended_answer", "author_notes", "design_cell")):
      errors.append(f"{record.get('record_id')}: hidden/author fields present")
    # soft validation for visible packages
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
      if field not in record:
        errors.append(f"{record.get('record_id')}: missing {field}")
    for key in record:
      if str(key).startswith("gold_"):
        errors.append(f"{record.get('record_id')}: gold field {key}")
  if errors:
    for err in errors:
      print(err, file=sys.stderr)
    return 1
  print(
    json.dumps(
      {
        "ok": True,
        "n_records": len(records),
        "package_sha256": package_bytes_hash(records),
        "record_ids": sorted(r["record_id"] for r in records),
      },
      sort_keys=True,
    )
  )
  return 0


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="T13 annotation programme utilities")
  parser.add_argument("--config", default=None, help="Reserved for future config overrides")
  parser.add_argument("--output", default=None, help="Output path for reports/packages")
  parser.add_argument("--dry-run", action="store_true")
  parser.add_argument("--overwrite", action="store_true")
  parser.add_argument("--package-a-id", default=None)
  parser.add_argument("--package-b-id", default=None)
  parser.add_argument("--validate-schema", action="store_true")
  parser.add_argument("--validate-candidates", dest="validate_candidates", default=None)
  parser.add_argument("--duplicates", dest="duplicates", default=None)
  parser.add_argument("--contamination", dest="contamination", default=None)
  parser.add_argument("--coverage", dest="coverage", default=None)
  parser.add_argument("--build-packages", dest="build_packages", default=None)
  parser.add_argument("--verify-package", dest="verify_package", default=None)
  return parser


def main(argv: list[str] | None = None) -> int:
  parser = build_parser()
  args = parser.parse_args(argv)
  if args.validate_schema:
    return cmd_validate_schema(args)
  if args.validate_candidates:
    args.path = args.validate_candidates
    return cmd_validate_candidates(args)
  if args.duplicates:
    args.path = args.duplicates
    return cmd_duplicates(args)
  if args.contamination:
    args.path = args.contamination
    return cmd_contamination(args)
  if args.coverage:
    args.path = args.coverage
    return cmd_coverage(args)
  if args.build_packages:
    args.path = args.build_packages
    return cmd_build_packages(args)
  if args.verify_package:
    args.path = args.verify_package
    return cmd_verify_package(args)
  parser.print_help()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
