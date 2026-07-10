#!/usr/bin/env python3
"""Convert CoDraw-iCR v2 authoritative TSV into canonical schema JSONL (T05).

Reads only ``data/raw/codraw-icr-v2/codraw-icr-v2.tsv`` (immutable). Never opens
``codraw-icr-v2_raw.tsv``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from ambiguity_manager.converters.codraw_icr_v2 import (  # noqa: E402
    AUTHORITATIVE_FILENAME,
    FORBIDDEN_FILENAME,
    run_conversion,
)
from ambiguity_manager.paths import ProjectPaths  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert CoDraw-iCR v2 authoritative TSV to canonical JSONL (read-only source)."
    )
    parser.add_argument("--source", type=Path, default=None, help="Authoritative TSV path")
    parser.add_argument("--output", type=Path, default=None, help="Canonical JSONL output path")
    parser.add_argument("--quarantine", type=Path, default=None, help="Quarantine JSONL output path")
    parser.add_argument("--summary", type=Path, default=None, help="Conversion summary JSON path")
    args = parser.parse_args()

    paths = ProjectPaths.from_repo_root(_REPO_ROOT)
    paths.ensure_project_dirs()

    source = args.source or (paths.data_raw / "codraw-icr-v2" / AUTHORITATIVE_FILENAME)
    if source.name == FORBIDDEN_FILENAME:
        print(f"error: refusing auxiliary source {FORBIDDEN_FILENAME}", file=sys.stderr)
        return 1

    output = args.output or (paths.data_interim / "codraw_icr_v2" / "codraw_icr_v2_canonical.jsonl")
    quarantine = args.quarantine or (paths.data_interim / "codraw_icr_v2" / "codraw_icr_v2_quarantine.jsonl")
    summary_path = args.summary or (paths.outputs / "metrics" / "codraw_icr_v2_conversion_summary.json")

    summary = run_conversion(source, output, quarantine, summary_path)

    print(f"source_rows_read : {summary['source_rows_read']}")
    print(f"rows_converted   : {summary['rows_converted']}")
    print(f"rows_quarantined : {summary['rows_quarantined']}")
    print(f"rows_skipped     : {summary['rows_skipped']}")
    print(f"output           : {summary['output_path']}")
    print(f"quarantine       : {summary['quarantine_path']}")
    print(f"summary          : {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
