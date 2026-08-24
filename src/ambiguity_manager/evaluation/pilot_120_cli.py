"""CLI for Pilot-120 v1 preflight, packages, freeze gates, and evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ambiguity_manager.evaluation import pilot_120 as p120


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ambiguity_manager.evaluation.pilot_120_cli",
        description="Pilot-120 v1 evaluation-only dataset tooling",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("preflight", help="Run hard preflight gates")
    sub.add_parser("status", help="Write/show STATUS.json including freeze blockers")
    sub.add_parser("materialize-source", help="Rebuild canonical source JSONL")
    sub.add_parser("build-packages", help="Build blind ANN-A / ANN-B delivery packages")
    sub.add_parser("agreement", help="Compute final-protocol agreement if A/B complete")
    sub.add_parser("adjudication-queue", help="Build disagreement-only adjudication packets")
    sub.add_parser("assemble-gold", help="Assemble final gold (requires closed gates)")
    sub.add_parser("freeze", help="Freeze Pilot-120 v1 (hard-fails if gates open)")
    sub.add_parser("compare-pilot", help="Compare final gold to historical pilot gold")

    p_imp = sub.add_parser("import-annotations", help="Import ANN-A or ANN-B submissions")
    p_imp.add_argument("--role", required=True, choices=["ANN-A", "ANN-B", "ann-a", "ann-b"])
    p_imp.add_argument("--from-dir", required=True, type=Path)

    p_val = sub.add_parser("validate-annotation", help="Validate one annotation against schema+input")
    p_val.add_argument("--annotation", required=True, type=Path)
    p_val.add_argument("--input", required=True, type=Path)

    p_eval = sub.add_parser("evaluate", help="Evaluate predictions against frozen Pilot-120 gold")
    p_eval.add_argument("--config", type=Path, default=None)
    p_eval.add_argument("--predictions", required=True, type=Path)

    args = parser.parse_args(argv)

    try:
        if args.cmd == "preflight":
            _print(p120.run_preflight())
        elif args.cmd == "status":
            _print(p120.write_status())
        elif args.cmd == "materialize-source":
            _print(p120.materialize_canonical_source())
        elif args.cmd == "build-packages":
            _print(p120.build_blind_packages())
        elif args.cmd == "agreement":
            _print(p120.compute_final_protocol_agreement())
        elif args.cmd == "adjudication-queue":
            _print(p120.build_disagreement_adjudication_queue())
        elif args.cmd == "assemble-gold":
            _print(p120.assemble_final_gold())
        elif args.cmd == "freeze":
            _print(p120.freeze())
        elif args.cmd == "compare-pilot":
            _print(p120.compare_to_historical_pilot())
        elif args.cmd == "import-annotations":
            _print(p120.import_annotations(role=args.role, from_dir=args.from_dir))
        elif args.cmd == "validate-annotation":
            errors = p120.validate_annotation_file(args.annotation, args.input)
            _print({"ok": not errors, "errors": errors})
            return 1 if errors else 0
        elif args.cmd == "evaluate":
            _print(p120.evaluate_predictions(args.predictions, config_path=args.config))
        else:  # pragma: no cover
            parser.error(f"unknown command {args.cmd}")
    except p120.Pilot120Error as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
