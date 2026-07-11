"""Merge completed T12 cluster shard outputs deterministically."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ambiguity_manager.model.cluster.run_state import load_manifest, merge_completed_shards, merge_result_canonical_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True, help="Shard plan JSON path.")
    parser.add_argument(
        "--shard-manifest",
        action="append",
        required=True,
        dest="shard_manifests",
        help="Completed shard manifest JSON path. Repeat per shard.",
    )
    parser.add_argument("--run-id", required=True, help="Expected run identifier.")
    parser.add_argument("--backend-config-hash", required=True, help="Backend/config identity hash.")
    parser.add_argument("--model-revision", required=True, help="Expected immutable model revision.")
    parser.add_argument("--container-sha256", required=True, help="Expected container SHA-256.")
    parser.add_argument("--output", type=Path, required=True, help="Merged JSONL output path.")
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Allow replacing an existing merged output file.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    plan_record_order = tuple(
        record_id for shard in plan["shard_record_ids"] for record_id in shard
    )

    manifests = []
    parsed_paths = []
    for manifest_path in args.shard_manifests:
        manifest = load_manifest(manifest_path)
        manifests.append(manifest)
        parsed_paths.append(Path(manifest.parsed_output_path))

    result = merge_completed_shards(
        shard_manifests=manifests,
        parsed_output_paths=parsed_paths,
        plan_record_order=plan_record_order,
        output_path=args.output,
        run_id=args.run_id,
        backend_config_hash=args.backend_config_hash,
        model_revision=args.model_revision,
        container_sha256=args.container_sha256,
        allow_overwrite=args.allow_overwrite,
    )
    print(merge_result_canonical_json(result))
    return 0 if result.status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
