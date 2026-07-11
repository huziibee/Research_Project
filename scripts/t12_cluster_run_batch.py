"""Run one T12 cluster synthetic shard through the persistent batch backend."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
from pathlib import Path

from ambiguity_manager.model.cluster.batch_runner import run_shard_batch
from ambiguity_manager.paths import repo_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime-config",
        type=Path,
        required=True,
        help="Path to the vLLM batch runtime configuration JSON.",
    )
    parser.add_argument(
        "--shard-plan",
        type=Path,
        required=True,
        help="Path to the deterministic shard plan JSON.",
    )
    parser.add_argument(
        "--shard-id",
        required=True,
        help="Shard identifier to execute, for example shard-000.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Run output directory; the directory name is used as the run identifier.",
    )
    parser.add_argument(
        "--preflight-result",
        type=Path,
        required=True,
        help="Path to a machine-readable preflight JSON summary.",
    )
    parser.add_argument(
        "--input-jsonl",
        type=Path,
        required=True,
        help="Synthetic JSONL input referenced by the shard plan.",
    )
    parser.add_argument(
        "--synthetic-declaration",
        type=Path,
        required=True,
        help="JSON declaration file that must contain {\"synthetic\": true}.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root containing configs/model and configs/environments.",
    )
    parser.add_argument(
        "--start-timestamp",
        required=True,
        help="Caller-supplied ISO timestamp for shard execution start.",
    )
    parser.add_argument(
        "--end-timestamp",
        required=True,
        help="Caller-supplied ISO timestamp for shard execution end.",
    )
    parser.add_argument(
        "--id-field",
        default="fixture_id",
        help="Stable unique ID field in the synthetic JSONL records.",
    )
    parser.add_argument(
        "--prompt-field",
        default="rendered_prompt",
        help="Rendered prompt field in the synthetic JSONL records.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate arguments and print the resolved configuration without starting a backend.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.repo_root or repo_root()
    preflight = json.loads(args.preflight_result.read_text(encoding="utf-8"))
    if args.dry_run:
        payload = {
            "status": "dry_run",
            "runtime_config": str(args.runtime_config),
            "shard_plan": str(args.shard_plan),
            "shard_id": args.shard_id,
            "run_dir": str(args.run_dir),
            "preflight_status": preflight.get("status"),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    result = run_shard_batch(
        repo_root=root,
        runtime_config_path=args.runtime_config,
        shard_plan_path=args.shard_plan,
        shard_id=args.shard_id,
        run_dir=args.run_dir,
        preflight_result=preflight,
        synthetic_declaration_path=args.synthetic_declaration,
        input_jsonl_path=args.input_jsonl,
        start_timestamp=args.start_timestamp,
        end_timestamp=args.end_timestamp,
        id_field=args.id_field,
        prompt_field=args.prompt_field,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if result.status == "completed":
        return 0
    return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
