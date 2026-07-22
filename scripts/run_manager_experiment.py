#!/usr/bin/env python3
"""CLI for model-independent manager experiment runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from ambiguity_manager.evaluation.evaluator import DeterministicEvaluator, GoldRecord, PredictionRecord
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput
from ambiguity_manager.systems.errors import OfficialRunBlockedError
from ambiguity_manager.systems.execution import ExperimentRunner, OfficialPrerequisites, load_json
from ambiguity_manager.systems.hashing import sha256_json
from ambiguity_manager.systems.variants import SYSTEM_IDS, list_systems


def _load_records(path: Path) -> list[SystemInput]:
  records: list[SystemInput] = []
  for line in path.read_text(encoding="utf-8").splitlines():
    if not line.strip():
      continue
    records.append(SystemInput.from_dict(json.loads(line)))
  return records


def _load_analyses(path: Path) -> dict[str, StructuredAnalysis]:
  raw = load_json(path)
  return {rid: StructuredAnalysis.from_dict(payload) for rid, payload in raw.items()}


def cmd_list_systems(_: argparse.Namespace) -> int:
  for item in list_systems():
    print(json.dumps(item, sort_keys=True))
  print(f"count={len(SYSTEM_IDS)}")
  return 0


def cmd_validate_config(args: argparse.Namespace) -> int:
  paths = ProjectPaths.from_repo_root(Path(__file__))
  config_path = Path(args.config) if args.config else paths.configs / "experiments" / "synthetic_smoke_v1.json"
  runner = ExperimentRunner(paths=paths)
  try:
    config = runner.validate_config(config_path)
  except Exception as exc:  # noqa: BLE001
    print(f"validation_failed: {exc}", file=sys.stderr)
    return 1
  print(json.dumps({"ok": True, "config_id": config.get("config_id"), "config_hash": sha256_json(config)}, sort_keys=True))
  return 0


def cmd_run_synthetic(args: argparse.Namespace) -> int:
  paths = ProjectPaths.from_repo_root(Path(__file__))
  config_path = Path(args.config)
  if not config_path.is_absolute():
    config_path = (Path.cwd() / config_path).resolve()
    if not config_path.is_file():
      config_path = paths.root / args.config
  config = load_json(config_path)
  if args.systems:
    config = dict(config)
    config["systems"] = list(args.systems)
  fixture_manifest = config.get("fixture_manifest", "tests/fixtures/t16_t24_synthetic/manifest.json")
  fixture_dir = paths.root / Path(fixture_manifest).parent
  records = _load_records(fixture_dir / "inputs.jsonl")
  analyses = _load_analyses(fixture_dir / "cached_analyses.json")
  runner = ExperimentRunner(paths=paths)
  output = Path(args.output) if args.output else None
  try:
    summary = runner.run(
      config=config,
      records=records,
      cached_analyses=analyses,
      resume=False,
      output_dir=output,
      dry_run=bool(args.dry_run),
    )
  except Exception as exc:  # noqa: BLE001
    print(f"run_failed: {exc}", file=sys.stderr)
    return 1
  print(json.dumps(summary, indent=2, sort_keys=True))
  return 0


def cmd_resume(args: argparse.Namespace) -> int:
  paths = ProjectPaths.from_repo_root(Path(__file__))
  run_dir = Path(args.run_id)
  if not run_dir.is_dir():
    run_dir = paths.outputs / "manager_experiments" / "synthetic" / args.run_id
  manifest = load_json(run_dir / "run_manifest.json")
  # The manifest is the source of truth for the exact config that produced
  # this run; resume must reuse it verbatim so its config_hash matches (the
  # resume contract refuses otherwise). Older manifests without an embedded
  # config snapshot fall back to the static synthetic-smoke config.
  config = manifest.get("config")
  if config is None:
    config_path = paths.configs / "experiments" / "synthetic_smoke_v1.json"
    config = load_json(config_path)
    config["run_mode"] = manifest.get("run_mode", "synthetic_smoke")
  fixture_manifest = config.get("fixture_manifest", "tests/fixtures/t16_t24_synthetic/manifest.json")
  fixture_dir = paths.root / Path(fixture_manifest).parent
  records = _load_records(fixture_dir / "inputs.jsonl")
  analyses = _load_analyses(fixture_dir / "cached_analyses.json")
  runner = ExperimentRunner(paths=paths)
  summary = runner.run(
    config=config,
    records=records,
    cached_analyses=analyses,
    run_id=manifest["run_id"],
    resume=True,
    output_dir=run_dir,
  )
  print(json.dumps(summary, indent=2, sort_keys=True))
  return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
  gold = [
    GoldRecord.from_dict(json.loads(line))
    for line in Path(args.gold).read_text(encoding="utf-8").splitlines()
    if line.strip()
  ]
  preds = [
    PredictionRecord.from_dict(json.loads(line))
    for line in Path(args.results_path).read_text(encoding="utf-8").splitlines()
    if line.strip()
  ]
  result = DeterministicEvaluator().evaluate(gold, preds, system_id=args.system)
  if isinstance(result, dict):
    # Multiple systems present and --system was not given: emit one
    # independently-scored bundle per system_id rather than merging them.
    output = {sid: bundle.to_dict() for sid, bundle in result.items()}
  else:
    output = result.to_dict()
  print(json.dumps(output, indent=2, sort_keys=True))
  return 0


def cmd_verify_run(args: argparse.Namespace) -> int:
  paths = ProjectPaths.from_repo_root(Path(__file__))
  runner = ExperimentRunner(paths=paths)
  report = runner.verify_run(Path(args.run_path))
  print(json.dumps(report, indent=2, sort_keys=True))
  return 0 if report.get("ok") else 1


def cmd_official_dry(args: argparse.Namespace) -> int:
  """Demonstrate that official mode remains gated."""
  paths = ProjectPaths.from_repo_root(Path(__file__))
  runner = ExperimentRunner(paths=paths)
  config = {
    "config_id": "official_gate_probe",
    "run_mode": "official",
    "systems": list(args.systems or SYSTEM_IDS),
  }
  try:
    runner.check_official_gates(
      prerequisites=OfficialPrerequisites.from_selected_identities(),
      systems=config["systems"],
      protected_labels_in_prompts=False,
    )
  except OfficialRunBlockedError as exc:
    print(json.dumps({"blocked": True, "missing": exc.missing}, sort_keys=True))
    return 2
  print(json.dumps({"blocked": False}, sort_keys=True))
  return 0


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="Ambiguity-manager experiment runner (model-independent foundation)")
  parser.add_argument("--list-systems", action="store_true")
  parser.add_argument("--validate-config", nargs="?", const="", metavar="CONFIG")
  parser.add_argument("--run-synthetic", dest="run_synthetic", metavar="CONFIG")
  parser.add_argument("--resume", metavar="RUN_ID")
  parser.add_argument("--evaluate", dest="results_path", metavar="RESULTS")
  parser.add_argument("--gold", metavar="GOLD")
  parser.add_argument("--verify-run", dest="run_path", metavar="RUN_PATH")
  parser.add_argument("--systems", nargs="+")
  parser.add_argument("--output")
  parser.add_argument("--dry-run", action="store_true")
  parser.add_argument("--system", help="Filter evaluation to one system_id")
  parser.add_argument("--probe-official-gates", action="store_true")
  return parser


def main(argv: list[str] | None = None) -> int:
  parser = build_parser()
  args = parser.parse_args(argv)
  # Normalise validate-config flag form.
  if args.list_systems:
    return cmd_list_systems(args)
  if args.validate_config is not None:
    args.config = args.validate_config or None
    return cmd_validate_config(args)
  if args.run_synthetic:
    args.config = args.run_synthetic
    return cmd_run_synthetic(args)
  if args.resume:
    args.run_id = args.resume
    return cmd_resume(args)
  if args.results_path:
    if not args.gold:
      print("--gold is required with --evaluate", file=sys.stderr)
      return 1
    return cmd_evaluate(args)
  if args.run_path:
    return cmd_verify_run(args)
  if args.probe_official_gates:
    return cmd_official_dry(args)
  parser.print_help()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
