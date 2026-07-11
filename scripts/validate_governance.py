#!/usr/bin/env python3
"""Validate repository governance artefacts."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.governance.validation import validate_repository_governance
from ambiguity_manager.paths import ProjectPaths


def main() -> int:
    paths = ProjectPaths.from_repo_root()
    errors = validate_repository_governance(paths.root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("governance validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
