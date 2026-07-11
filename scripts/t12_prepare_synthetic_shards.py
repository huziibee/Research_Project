"""Prepare deterministic synthetic shard plans for T12 cluster execution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ambiguity_manager.model.cluster.sharding import ShardPlanningError, plan_shards_from_jsonl, plan_to_canonical_json
from ambiguity_manager.paths import repo_relative_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Synthetic JSONL input path.")
    parser.add_argument(
        "--synthetic-declaration",
        type=Path,
        required=True,
        help="JSON declaration file that must contain {\"synthetic\": true}.",
    )
    parser.add_argument("--id-field", default="fixture_id", help="Stable unique ID field name.")
    parser.add_argument("--shard-count", type=int, required=True, help="Positive shard count.")
    parser.add_argument("--created-timestamp", required=True, help="Caller-supplied ISO timestamp.")
    parser.add_argument("--output", type=Path, required=True, help="Output shard plan JSON path.")
    return parser


def _require_synthetic_declaration(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("synthetic") is not True:
        raise ValueError("input_not_explicitly_marked_synthetic")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _require_synthetic_declaration(args.synthetic_declaration)
        plan = plan_shards_from_jsonl(
            args.input,
            id_field=args.id_field,
            shard_count=args.shard_count,
            created_timestamp=args.created_timestamp,
            input_source=repo_relative_path(args.input),
        )
    except (ShardPlanningError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, sort_keys=True))
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    canonical = plan_to_canonical_json(plan)
    args.output.write_text(canonical + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "pass",
                "record_count": plan.record_count,
                "shard_count": plan.shard_count,
                "input_sha256": plan.input_sha256,
                "output": repo_relative_path(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
