"""Run T12 Stage D-Final synthetic generation pipeline smoke (local entrypoint)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ambiguity_manager.paths import repo_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the T12 D-Final synthetic response-mode probe and "
            "four-record generation pipeline smoke."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/cluster/t12_d_final_smoke.json"),
        help="Path to the frozen D-Final smoke configuration JSON.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Unique run output directory; the directory name becomes the run identifier.",
    )
    parser.add_argument(
        "--preflight-result",
        type=Path,
        required=True,
        help="Machine-readable preflight JSON summary with status=pass.",
    )
    parser.add_argument(
        "--source-identity-manifest",
        type=Path,
        required=True,
        help="Runtime source-identity manifest JSON for git-archive transfer verification.",
    )
    parser.add_argument(
        "--source-archive",
        type=Path,
        required=True,
        help="Retained git-archive file whose SHA-256 must match the source-identity manifest.",
    )
    parser.add_argument(
        "--slurm-log-path",
        type=str,
        required=True,
        help="Sanitised external Slurm log path recorded in run_manifest.json.",
    )
    parser.add_argument(
        "--snapshot-path",
        type=Path,
        default=None,
        help="Offline tokenizer snapshot directory for live runs.",
    )
    parser.add_argument(
        "--measurement-timestamp",
        required=True,
        help="ISO timestamp recorded in run-scoped verification evidence.",
    )
    parser.add_argument(
        "--extracted-source-root",
        type=Path,
        default=None,
        help="Extracted source tree root for optional .git cross-check.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root containing configs and synthetic fixtures.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    from ambiguity_manager.model.cluster.generation_pipeline_runner import (
        load_d_final_config,
        run_d_final_smoke,
    )

    parser = build_parser()
    args = parser.parse_args(argv)
    root = args.repo_root or repo_root()
    config = load_d_final_config(args.config, root=root)
    preflight = json.loads(args.preflight_result.read_text(encoding="utf-8"))
    result = run_d_final_smoke(
        run_dir=args.run_dir,
        preflight_result=preflight,
        config=config,
        root=root,
        source_identity_manifest_path=args.source_identity_manifest,
        source_archive=args.source_archive,
        extracted_source_root=args.extracted_source_root or root,
        slurm_log_path=args.slurm_log_path,
        measurement_timestamp=args.measurement_timestamp,
        snapshot_path=args.snapshot_path,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
