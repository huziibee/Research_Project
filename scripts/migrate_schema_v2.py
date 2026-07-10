#!/usr/bin/env python3
"""Migrate completed v1 canonical artefacts to schema v2."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
  sys.path.insert(0, str(_REPO_ROOT / "src"))

from ambiguity_manager.migration.run_migration import SchemaV2MigrationError, migrate_schema_v2  # noqa: E402
from ambiguity_manager.paths import ProjectPaths  # noqa: E402


def main() -> int:
  parser = argparse.ArgumentParser(description="Migrate completed v1 artefacts to schema v2 (T10).")
  group = parser.add_mutually_exclusive_group(required=True)
  group.add_argument("--validate-only", action="store_true", help="Validate migration without publishing.")
  group.add_argument("--publish", action="store_true", help="Validate and publish schema v2 outputs.")
  args = parser.parse_args()

  paths = ProjectPaths.from_repo_root(_REPO_ROOT)
  paths.ensure_project_dirs()

  try:
    result = migrate_schema_v2(_REPO_ROOT, publish=args.publish)
  except SchemaV2MigrationError as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    return 1

  print(json.dumps({k: v for k, v in result.items() if k != "pool_result"}, indent=2))
  if args.publish:
    print("published: true")
  else:
    print("published: false")
  print(f"validation_timestamp: {datetime.now(timezone.utc).isoformat()}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
