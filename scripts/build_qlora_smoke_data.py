#!/usr/bin/env python3
"""Regenerate the deterministic QLoRA technical-smoke data subset (T27 Phase E).

Builds a small (32-64 record) deterministic subset of ``source_train`` only
(see ``data/development/source_splits_v1/``), preferring the strongest
structured-target records with multi-source and multi-category coverage,
under ``data/development/qlora_smoke_v1/``.

Requires ``data/development/source_splits_v1/`` and
``data/processed/weak_pool/weak_pool_canonical.jsonl`` to already exist (run
``python scripts/build_source_data_splits.py`` first if not).

Usage:
    python scripts/build_qlora_smoke_data.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.model.qlora_smoke_data import (  # noqa: E402
    OUTPUT_DIR_REL,
    SmokeDataError,
    build_qlora_smoke_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    try:
        result = build_qlora_smoke_dataset(publish=True)
    except SmokeDataError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    manifest = result["manifest"]
    coverage = result["coverage_report"]

    print(f"Built QLoRA smoke data subset into {OUTPUT_DIR_REL}")
    print(f"record_count={manifest['record_count']} seed={manifest['seed']}")
    print(f"manifest_hash={manifest['manifest_hash']}")
    print(f"dataset_counts_in_selection={coverage['dataset_counts_in_selection']}")
    for category_id, entry in coverage["categories"].items():
        print(
            f"category={category_id} legitimately_supported={entry['legitimately_supported']} "
            f"selected={entry['selected_record_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
