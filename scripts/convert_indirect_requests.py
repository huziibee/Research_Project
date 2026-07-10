#!/usr/bin/env python3
"""Convert IndirectRequests Arrow IPC streams into canonical schema JSONL (T04)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from ambiguity_manager.converters.indirect_requests import (  # noqa: E402
    default_raw_root,
    run_conversion,
)
from ambiguity_manager.paths import ProjectPaths  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert IndirectRequests Arrow shards to canonical JSONL (read-only source)."
    )
    parser.add_argument("--source-root", type=Path, default=None, help="IndirectRequests raw root")
    parser.add_argument("--output", type=Path, default=None, help="Canonical JSONL output path")
    parser.add_argument("--quarantine", type=Path, default=None, help="Quarantine JSONL output path")
    parser.add_argument("--summary", type=Path, default=None, help="Conversion summary JSON path")
    args = parser.parse_args()

    paths = ProjectPaths.from_repo_root(_REPO_ROOT)
    paths.ensure_project_dirs()

    source_root = args.source_root or default_raw_root(_REPO_ROOT)
    output = args.output or (
        paths.data_interim / "indirect_requests" / "indirect_requests_canonical.jsonl"
    )
    quarantine = args.quarantine or (
        paths.data_interim / "indirect_requests" / "indirect_requests_quarantine.jsonl"
    )
    summary_path = args.summary or (
        paths.outputs / "metrics" / "indirect_requests_conversion_summary.json"
    )

    summary = run_conversion(source_root, output, quarantine, summary_path)

    print(f"source_rows_read : {summary['source_rows_read']}")
    print(f"rows_converted   : {summary['rows_converted']}")
    print(f"rows_ambiguous   : {summary['rows_ambiguous']}")
    print(f"rows_concrete    : {summary['rows_concrete_target']}")
    print(f"rows_quarantined : {summary['rows_quarantined']}")
    print(f"rows_skipped     : {summary['rows_skipped']}")
    print(f"rows_per_split   : {summary['rows_per_split']}")
    print(f"output           : {summary['output_path']}")
    print(f"quarantine       : {summary['quarantine_path']}")
    print(f"summary          : {summary['summary_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
