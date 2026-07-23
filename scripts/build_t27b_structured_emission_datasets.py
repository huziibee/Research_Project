#!/usr/bin/env python3
"""Build T27B structured-emission recovery datasets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.model.t27b_datasets import build_all_t27b_datasets  # noqa: E402


def main() -> int:
    result = build_all_t27b_datasets(publish=True)
    print(
        json.dumps(
            {
                "sealed_ids": result["sealed_ids"],
                "diagnostic_ids": result["diagnostic_ids"],
                "train_count": result["train_manifest"]["record_count"],
                "mean_supervised_token_percentage": result["supervision_density_report"][
                    "mean_supervised_token_percentage"
                ],
                "paths": result.get("paths"),
                "final_manifest_hash": result["final_manifest"].get("manifest_hash"),
                "train_manifest_hash": result["train_manifest"].get("manifest_hash"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
