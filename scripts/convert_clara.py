#!/usr/bin/env python3
"""Convert the CLARA/SaGC agument.json into canonical schema JSONL (T07).

Reads only ``data/raw/CLARA-Dataset/data/agument.json`` (immutable) and writes
canonical, quarantine, excluded, and conversion-summary artefacts through the
guarded write API.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from ambiguity_manager.converters.clara import default_source_path, run_conversion  # noqa: E402
from ambiguity_manager.paths import ProjectPaths  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert CLARA/SaGC to canonical JSONL (read-only source).")
    parser.add_argument("--source", type=Path, default=None, help="CLARA agument.json path")
    parser.add_argument("--output", type=Path, default=None, help="Canonical JSONL output path")
    parser.add_argument("--quarantine", type=Path, default=None, help="Quarantine JSONL output path")
    parser.add_argument("--excluded", type=Path, default=None, help="Excluded-by-policy JSONL output path")
    parser.add_argument("--summary", type=Path, default=None, help="Conversion summary JSON path")
    args = parser.parse_args()

    paths = ProjectPaths.from_repo_root(_REPO_ROOT)
    paths.ensure_project_dirs()

    source = args.source or default_source_path(_REPO_ROOT)
    output = args.output or (paths.data_interim / "clara" / "clara_canonical.jsonl")
    quarantine = args.quarantine or (paths.data_interim / "clara" / "clara_quarantine.jsonl")
    excluded = args.excluded or (paths.data_interim / "clara" / "clara_excluded.jsonl")
    summary_path = args.summary or (paths.outputs / "metrics" / "clara_conversion_summary.json")

    summary = run_conversion(source, output, quarantine, excluded, summary_path)

    print(f"source_rows_read        : {summary['source_rows_read']}")
    print(f"rows_converted          : {summary['rows_converted']}")
    print(f"rows_excluded_by_policy : {summary['rows_excluded_by_policy']}")
    print(f"rows_quarantined        : {summary['rows_quarantined']}")
    print(f"rows_skipped            : {summary['rows_skipped']}")
    print(f"output                  : {summary['output_path']}")
    print(f"quarantine              : {summary['quarantine_path']}")
    print(f"excluded                : {summary['excluded_path']}")
    print(f"summary                 : {summary['summary_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
