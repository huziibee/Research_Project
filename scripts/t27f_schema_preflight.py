#!/usr/bin/env python3
"""Run T27F schema preflight without loading a model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.model.schema_preflight import run_schema_preflight  # noqa: E402


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
    print(json.dumps({"passed": payload["passed"], "output": str(args.output), "tasks": len(payload["tasks"])}, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
