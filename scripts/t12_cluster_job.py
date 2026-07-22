#!/usr/bin/env python3
"""Local CLI for T12 Slurm run / status / poll / pull / verify."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running without PYTHONPATH when invoked from repo scripts/
_REPO_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

from ambiguity_manager.model.cluster.job_operator import (  # noqa: E402
    ClusterJobOperator,
    OperatorError,
)
from ambiguity_manager.paths import ProjectPaths  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safe local Slurm operator for T12 cluster jobs (run/status/poll/pull/verify).",
    )
    parser.add_argument("--run", metavar="PROFILE", help="Submit a profile (e.g. canary).")
    parser.add_argument(
        "--candidate-id",
        metavar="ID",
        help="Allowlisted model candidate id for GPU bake-off profiles.",
    )
    parser.add_argument(
        "--status",
        nargs="?",
        const="latest",
        metavar="ID",
        help="Show Slurm status for latest or a job/run ID.",
    )
    parser.add_argument(
        "--poll",
        nargs="?",
        const="latest",
        metavar="ID",
        help="Poll until terminal state (or local timeout).",
    )
    parser.add_argument(
        "--pull",
        nargs="?",
        const="latest",
        metavar="ID",
        help="Pull remote results for latest or a run ID.",
    )
    parser.add_argument(
        "--verify",
        nargs="?",
        const="latest",
        metavar="ID",
        help="Verify pulled run manifest hashes/sizes/row counts.",
    )
    parser.add_argument("--list", action="store_true", help="List recorded local runs.")
    parser.add_argument("--dry-run", action="store_true", help="Package locally; do not SSH/submit.")
    parser.add_argument("--interval", type=float, default=30.0, help="Poll interval seconds.")
    parser.add_argument("--timeout", type=float, default=3600.0, help="Local poll timeout seconds.")
    parser.add_argument("--ssh-alias", default="wits-mscluster", help="SSH config Host alias.")
    parser.add_argument(
        "--force-pull",
        action="store_true",
        help="Allow replacing an existing local pull directory (never deletes remote).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    actions = [
        bool(args.run),
        args.status is not None,
        args.poll is not None,
        args.pull is not None and not args.run and args.poll is None,
        args.verify is not None,
        bool(args.list),
    ]
    # Allow combinations: --run ... --poll --pull ; --poll ... --pull
    if args.run:
        pass
    elif args.poll is not None:
        pass
    elif sum(1 for flag in (args.status is not None, args.pull is not None, args.verify is not None, args.list) if flag) != 1:
        if not any(
            [
                args.status is not None,
                args.pull is not None,
                args.verify is not None,
                args.list,
            ]
        ):
            parser.error("Specify one of --run/--status/--poll/--pull/--verify/--list")

    root = ProjectPaths.from_repo_root(Path(__file__)).root
    operator = ClusterJobOperator(
        repo_root=root,
        ssh_alias=args.ssh_alias,
        dry_run=args.dry_run,
    )

    try:
        if args.run:
            poll = args.poll is not None
            pull = args.pull is not None
            operator.run_profile(
                args.run,
                candidate_id=args.candidate_id,
                poll=poll,
                pull=pull,
                interval=args.interval,
                timeout=args.timeout,
            )
            return 0
        if args.poll is not None:
            operator.poll(
                args.poll,
                interval=args.interval,
                timeout=args.timeout,
                pull=args.pull is not None,
            )
            return 0
        if args.status is not None:
            operator.status(args.status)
            return 0
        if args.pull is not None:
            operator.pull(args.pull, force=args.force_pull)
            return 0
        if args.verify is not None:
            operator.verify(args.verify)
            return 0
        if args.list:
            operator.list_runs()
            return 0
    except OperatorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    parser.error("No action selected")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
