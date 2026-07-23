#!/usr/bin/env python3
"""Cluster entry point for T27B structured-emission recovery QLoRA.

Requires real_cluster_training mode. Never silently falls back to mock.

Invoked by configs/cluster/t12_job_profiles.json#profiles.qlora_structured_emission_recovery::

    python scripts/t12_cluster_job.py --run qlora_structured_emission_recovery --poll --pull
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ARCHIVE_SHA_RE = re.compile(r"^[0-9a-f]{64}$")

from ambiguity_manager.model.qlora_structured_emission_recovery import (  # noqa: E402
    QloraStructuredEmissionRecoveryError,
    run_structured_emission_recovery_training,
)
from ambiguity_manager.paths import repo_root  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-archive-sha256", required=True)
    parser.add_argument("--source-identity-manifest", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=None)
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

    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "source_identity_manifest.json").write_text(
        manifest_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    try:
        outcome = run_structured_emission_recovery_training(
            result_dir=result_dir,
            run_id=args.run_id,
            root=root,
            require_real_mode=True,
            force_mock=False,
        )
    except QloraStructuredEmissionRecoveryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    result = outcome["result"]
    mode = result.get("mode")
    success = bool(result.get("success"))
    print(
        f"QLORA_STRUCTURED_EMISSION_RECOVERY_{'PASS' if success else 'FAIL'} "
        f"run_id={args.run_id} mode={mode}"
    )
    print(f"selected_base_model={result.get('selected_base_model')}")
    print(
        f"adapter_id={result.get('adapter_id')} "
        f"record_count={result.get('record_count')} "
        f"validation_record_count={result.get('validation_record_count')}"
    )
    resume = result.get("resume_components") or {}
    print(f"full_resume_ok={resume.get('full_resume_ok')}")
    summary = result.get("structured_output_summary") or {}
    print(
        f"structured_accepted={summary.get('accepted_count')} "
        f"status_counts={summary.get('status_counts')}"
    )
    if not success:
        print(f"failure_reason={result.get('failure_reason')}", file=sys.stderr)
        return 1
    if mode != "real_cluster_training":
        print(f"ERROR: expected real_cluster_training, got {mode}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
