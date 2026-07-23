#!/usr/bin/env python3
"""Build the task-aligned QLoRA smoke dataset v2 and frozen validation set."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.model.qlora_task_aligned_smoke_data import (  # noqa: E402
    build_task_aligned_smoke_dataset,
)


def main() -> int:
    result = build_task_aligned_smoke_dataset(publish=True)
    manifest = result["manifest"]
    print(
        json.dumps(
            {
                "record_count": manifest["record_count"],
                "validation_record_count": manifest["validation_record_count"],
                "manifest_hash": manifest.get("manifest_hash"),
                "datasets": result["coverage"]["datasets"],
                "validation_ids": manifest["validation_record_ids"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
