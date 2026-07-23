#!/usr/bin/env python3
"""Build T27C task-conditioned smoke / diagnostic / sealed datasets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

from ambiguity_manager.model.t27c_datasets import build_t27c_datasets  # noqa: E402


def main() -> int:
    summary = build_t27c_datasets()
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
