#!/usr/bin/env python3
"""Four-record development transport smoke for an allowlisted model candidate."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

from ambiguity_manager.model.bakeoff_provider import (  # noqa: E402
    BakeoffProviderError,
    add_standard_run_cli,
    parse_standard_run_cli,
    run_transport_smoke,
)
from ambiguity_manager.paths import repo_root  # noqa: E402


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    add_standard_run_cli(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    candidate_id = parse_standard_run_cli(args)
    root = args.repo_root or repo_root()
    try:
        result = run_transport_smoke(
            candidate_id=candidate_id,
            result_dir=args.result_dir.resolve(),
            run_id=args.run_id,
            source_commit=args.source_commit,
            source_archive_sha256=args.source_archive_sha256,
            source_identity_manifest=args.source_identity_manifest,
            root=root,
        )
    except BakeoffProviderError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"TRANSPORT_{result['status'].upper()} candidate={candidate_id}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
