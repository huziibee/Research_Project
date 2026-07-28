#!/usr/bin/env python3
"""Run T27F schema preflight without loading a model."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.model.schema_preflight import run_schema_preflight  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "configs/model/evidence/t27f_schema_preflight.json")
    parser.add_argument("--result-dir", type=Path, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--source-commit", default=None)
    parser.add_argument("--source-archive-sha256", default=None)
    parser.add_argument("--source-identity-manifest", type=Path, default=None)
    args = parser.parse_args()
    payload = run_schema_preflight(ROOT)
    if args.result_dir is not None:
        args.output = args.result_dir / "t27f_schema_preflight.json"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.result_dir is not None:
        manifest = {
            "schema_version": "1.0.0",
            "run_id": args.run_id,
            "profile": "t27f_schema_preflight",
            "source_commit_sha": args.source_commit,
            "source_archive_sha256": args.source_archive_sha256,
            "success": bool(payload["passed"]),
            "development_only": True,
            "valid_for_official_use": False,
            "files": [{
                "relative_path": args.output.name,
                "sha256": _sha256(args.output),
                "size_bytes": args.output.stat().st_size,
            }],
        }
        (args.result_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "output": str(args.output), "tasks": len(payload["tasks"])}, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
