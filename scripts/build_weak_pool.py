#!/usr/bin/env python3
"""Build the T09 weak labelled pools from approved canonical converter outputs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from ambiguity_manager.paths import ProjectPaths  # noqa: E402
from ambiguity_manager.weak_pool import WeakPoolBuildError, build_weak_pool, production_spec  # noqa: E402


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = result.stdout.strip()
    return commit or None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build weak labelled pools (T09).")
    parser.parse_args()

    paths = ProjectPaths.from_repo_root(_REPO_ROOT)
    paths.ensure_project_dirs()
    (paths.outputs / "manifests").mkdir(parents=True, exist_ok=True)

    inputs, outputs = production_spec(_REPO_ROOT)
    try:
        result = build_weak_pool(inputs, outputs, publish=True)
    except WeakPoolBuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    print(f"primary_count      : {result['primary_count']}")
    print(f"auxiliary_count    : {result['auxiliary_count']}")
    print(f"membership_count   : {result['membership_count']}")
    print(f"git_commit         : {_git_commit() or 'unavailable'}")
    print(f"build_timestamp    : {datetime.now(timezone.utc).isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
