#!/usr/bin/env python3
"""Clean-path package verification; model loading is opt-in and fail-closed."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ambiguity_manager.model.t28_trainer import verify_package_checksums  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--base-revision", required=True)
    p.add_argument("--schema-registry", type=Path, required=True)
    a = p.parse_args()
    manifest = json.loads((a.package / "package_manifest.json").read_text(encoding="utf-8"))
    passed = verify_package_checksums(a.package, manifest) and manifest.get("identity", {}).get("base_revision") == a.base_revision
    evidence = {"status": "VERIFY_PASSED" if passed else "VERIFY_FAILED", "package_checksums": passed, "base_revision": a.base_revision, "protected_data_accessed": False, "schema_registry": str(a.schema_registry), "clean_path": True}
    a.output.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
