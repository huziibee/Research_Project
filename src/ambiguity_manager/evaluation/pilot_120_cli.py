"""CLI for Pilot-120 final-protocol status, freeze, and evaluation handoff."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ambiguity_manager.evaluation.pilot_120 import (
  Pilot120FreezeError,
  Pilot120LoaderError,
  current_freeze_blockers,
  discover_prerequisite_artifacts,
  freeze_pilot_120_v1,
  load_pilot_120_for_evaluation,
  prepare_blind_packages_from_source,
  run_agreement_and_queue,
  write_blocked_status,
  write_eval_handoff,
)
from ambiguity_manager.paths import ProjectPaths


def _cmd_status(_: argparse.Namespace) -> int:
  status = write_blocked_status()
  print(json.dumps(status, indent=2, sort_keys=True))
  return 0 if status.get("frozen") else 2


def _cmd_discover(_: argparse.Namespace) -> int:
  print(json.dumps(discover_prerequisite_artifacts(), indent=2, sort_keys=True))
  return 0


def _cmd_blockers(_: argparse.Namespace) -> int:
  blockers = current_freeze_blockers()
  print(json.dumps({"blockers": blockers, "n": len(blockers)}, indent=2, sort_keys=True))
  return 0 if not blockers else 2


def _cmd_prepare_blind(_: argparse.Namespace) -> int:
  try:
    result = prepare_blind_packages_from_source()
  except Pilot120FreezeError as exc:
    print(str(exc), file=sys.stderr)
    return 2
  print(json.dumps(result, indent=2, sort_keys=True))
  return 0


def _cmd_agreement(_: argparse.Namespace) -> int:
  try:
    result = run_agreement_and_queue()
  except Exception as exc:  # noqa: BLE001 — CLI boundary
    print(str(exc), file=sys.stderr)
    return 2
  # Avoid dumping full agreement nested twice
  summary = {
    "disagreement_count": result["disagreement_count"],
    "agreement": result["agreement"],
  }
  print(json.dumps(summary, indent=2, sort_keys=True))
  return 0


def _cmd_freeze(_: argparse.Namespace) -> int:
  try:
    report = freeze_pilot_120_v1()
  except Pilot120FreezeError as exc:
    write_blocked_status()
    print(str(exc), file=sys.stderr)
    return 2
  print(json.dumps(report, indent=2, sort_keys=True))
  return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
  try:
    gold = load_pilot_120_for_evaluation(purpose=args.purpose)
  except Pilot120LoaderError as exc:
    print(str(exc), file=sys.stderr)
    return 2
  pred_path = Path(args.predictions)
  if not pred_path.is_file():
    print(f"predictions not found: {pred_path}", file=sys.stderr)
    return 2
  # Minimal scoring handoff: count id overlap; full metric suite remains T24 evaluator.
  predictions = []
  with pred_path.open(encoding="utf-8") as handle:
    for line in handle:
      line = line.strip()
      if line:
        predictions.append(json.loads(line))
  gold_ids = {r["record_id"] for r in gold}
  pred_ids = {r.get("record_id") for r in predictions}
  summary = {
    "evaluation_set_id": "pilot_120_v1",
    "n_gold": len(gold),
    "n_predictions": len(predictions),
    "n_scored": len(gold_ids & pred_ids),
    "missing_predictions": sorted(gold_ids - pred_ids),
    "extra_predictions": sorted(pred_ids - gold_ids),
    "note": (
      "Use DeterministicEvaluator from ambiguity_manager.evaluation for official metrics; "
      "this command verifies evaluation-only loading and prediction coverage."
    ),
  }
  if args.out:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
  print(json.dumps(summary, indent=2, sort_keys=True))
  return 0


def _cmd_handoff(_: argparse.Namespace) -> int:
  path = write_eval_handoff()
  print(json.dumps({"eval_handoff": str(path)}, indent=2, sort_keys=True))
  return 0


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(prog="pilot_120_cli")
  sub = parser.add_subparsers(dest="command", required=True)

  p_status = sub.add_parser("status", help="Write and print Pilot-120 / Full-1000 status")
  p_status.set_defaults(func=_cmd_status)

  p_disc = sub.add_parser("discover", help="Discover assumed prerequisite artifacts")
  p_disc.set_defaults(func=_cmd_discover)

  p_block = sub.add_parser("blockers", help="List freeze blockers")
  p_block.set_defaults(func=_cmd_blockers)

  p_blind = sub.add_parser("prepare-blind", help="Build blind ANN-A/ANN-B packages from source")
  p_blind.set_defaults(func=_cmd_prepare_blind)

  p_agr = sub.add_parser("agreement", help="Compute final-protocol agreement + disagreement queue")
  p_agr.set_defaults(func=_cmd_agreement)

  p_freeze = sub.add_parser("freeze", help="Freeze Pilot-120 when all gates are closed")
  p_freeze.set_defaults(func=_cmd_freeze)

  p_eval = sub.add_parser("evaluate", help="Evaluation-only load + prediction coverage check")
  p_eval.add_argument("--config", required=True, help="configs/evaluation/pilot_120_v1.json")
  p_eval.add_argument("--predictions", required=True, help="System predictions JSONL")
  p_eval.add_argument("--purpose", default="evaluation")
  p_eval.add_argument("--out", default=None)
  p_eval.set_defaults(func=_cmd_evaluate)

  p_hand = sub.add_parser("handoff", help="Write evaluation handoff config")
  p_hand.set_defaults(func=_cmd_handoff)

  return parser


def main(argv: list[str] | None = None) -> int:
  # Ensure repo root resolution works when invoked as module
  ProjectPaths.from_repo_root()
  parser = build_parser()
  args = parser.parse_args(argv)
  return int(args.func(args))


if __name__ == "__main__":
  raise SystemExit(main())
