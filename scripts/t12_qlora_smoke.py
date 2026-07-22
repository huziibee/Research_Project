#!/usr/bin/env python3
"""Cluster entry point for the QLoRA technical smoke (T27 Phase E).

Runs :func:`ambiguity_manager.model.qlora_smoke.run_smoke_training` and
always finalises evidence (``qlora_smoke_result.json``,
``adapter_identity.json`` once at least one checkpoint exists,
``loss_mask_summary.json``, ``run_manifest.json``) under ``--result-dir``,
whether the smoke succeeds or fails.

``force_mock`` is left at the library default (``False``) here: on a real
GPU node with the pinned training container's dependencies importable, this
takes the real 4-bit QLoRA path (see ``run_real_qlora_smoke`` in
``qlora_smoke.py``); anywhere those dependencies are missing (including any
accidental invocation off-cluster), it transparently falls back to the
deterministic CPU-only mock contract proof rather than failing outright.

Invoked by ``configs/cluster/t12_job_profiles.json#profiles.qlora_smoke`` via:

    python scripts/t12_cluster_job.py --run qlora_smoke --poll --pull
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

from ambiguity_manager.model.bakeoff_provider import ARCHIVE_SHA_RE, COMMIT_SHA_RE  # noqa: E402
from ambiguity_manager.model.qlora_smoke import (  # noqa: E402
    QloraSmokeError,
    run_smoke_training,
)
from ambiguity_manager.paths import repo_root  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-archive-sha256", required=True)
    parser.add_argument(
        "--source-identity-manifest",
        type=Path,
        required=True,
        help="Retained source-identity manifest from operator packaging (recorded, not re-verified here).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root containing configs and the smoke data subset.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.repo_root or repo_root()
    result_dir = args.result_dir.resolve()

    if not COMMIT_SHA_RE.match(args.source_commit):
        print("ERROR: invalid_source_commit", file=sys.stderr)
        return 1
    if not ARCHIVE_SHA_RE.match(args.source_archive_sha256):
        print("ERROR: invalid_source_archive_sha256", file=sys.stderr)
        return 1
    manifest_path = args.source_identity_manifest
    if not manifest_path.is_file():
        print(f"ERROR: source_identity_manifest_missing:{manifest_path}", file=sys.stderr)
        return 1

    # Copy the source-identity manifest into the result dir before training
    # starts so it is present for evidence pull/verify regardless of whether
    # the run below succeeds or fails; run_smoke_training's own emptiness
    # guard only checks for its own evidence files, not this one.
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "source_identity_manifest.json").write_text(
        manifest_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    try:
        outcome = run_smoke_training(
            result_dir=result_dir,
            run_id=args.run_id,
            root=root,
        )
    except QloraSmokeError as exc:
        # Preconditions (missing selected_base_model, non-empty result dir,
        # invalid config, missing smoke dataset) fail before any run started,
        # so no evidence has been written yet; report and exit non-zero.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    result = outcome["result"]
    print(f"QLORA_SMOKE_{'PASS' if result['success'] else 'FAIL'} run_id={args.run_id} mode={result['mode']}")
    print(f"selected_base_model={result['selected_base_model']}")
    print(f"adapter_id={result['adapter_id']} record_count={result['record_count']}")
    if not result["success"]:
        print(f"failure_reason={result['failure_reason']}", file=sys.stderr)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
