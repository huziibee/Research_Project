#!/usr/bin/env python3
"""Regenerate the deterministic source-development split programme (T15).

Builds source_train / source_dev / source_holdout (primary weak pool) and
auxiliary_train / auxiliary_dev (ClariQ) splits, eligibility manifests,
leakage/coverage reports, and canonical hashes under
``data/development/source_splits_v1/``.

Usage:
    python scripts/build_source_data_splits.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.data.source_splits import (  # noqa: E402
    OUTPUT_DIR,
    build_source_splits,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    result = build_source_splits(publish=True)
    manifest = result["manifest"]
    coverage = result["coverage_report"]

    print(f"Built source data split programme into {OUTPUT_DIR}")
    print(f"manifest_hash={manifest['manifest_hash']}")
    print(f"record_counts={manifest['record_counts']}")
    print(
        "primary percentages="
        f"{ {k: round(v, 3) for k, v in coverage['primary']['percentages'].items()} } "
        f"within_tolerance={coverage['primary']['within_tolerance']}"
    )
    print(
        "auxiliary percentages="
        f"{ {k: round(v, 3) for k, v in coverage['auxiliary']['percentages'].items()} } "
        f"within_tolerance={coverage['auxiliary']['within_tolerance']}"
    )
    print(f"leakage_all_checks_passed={result['leakage_report']['all_checks_passed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
