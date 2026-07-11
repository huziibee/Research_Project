"""Validate supplied T12 cluster runtime facts (Stage C1 CPU-only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ambiguity_manager.model.cluster.preflight import run_preflight
from ambiguity_manager.paths import repo_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime-facts",
        type=Path,
        required=True,
        help="Path to runtime facts JSON supplied by a cluster probe or test fixture.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root containing configs/model and configs/environments.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the machine-readable preflight JSON summary.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.repo_root or repo_root()
    facts = json.loads(args.runtime_facts.read_text(encoding="utf-8"))
    result = run_preflight(facts, repo_root=root)
    payload = json.dumps(result.to_dict(), indent=2, sort_keys=True)
    print(payload)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0 if result.status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
