#!/usr/bin/env python3
"""T28 dev-only inference boundary.

This entry point refuses to run unless the supplied manifest is exclusively
source_dev. The model backend is injected by the pinned cluster wrapper; no
unconstrained fallback is permitted here.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ambiguity_manager.model.t28 import T28Error, assert_dev_only  # noqa: E402
from ambiguity_manager.model.t28_trainer import iter_jsonl, sha256_file  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dev-manifest", type=Path, required=True)
    p.add_argument("--expected-sha256", required=True)
    p.add_argument("--adapter", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--raw-output", type=Path, required=True)
    p.add_argument("--validate-only", action="store_true")
    a = p.parse_args()
    if sha256_file(a.dev_manifest) != a.expected_sha256:
        raise T28Error("dev_manifest_hash_mismatch")
    rows = list(iter_jsonl(a.dev_manifest))
    assert_dev_only(rows)
    if not a.adapter.exists():
        raise T28Error("adapter_missing")
    if not a.validate_only:
        raise T28Error("inference_backend_must_be_pinned_cluster_runtime")
    a.raw_output.write_text("", encoding="utf-8")
    a.output.write_text(json.dumps({"status": "DEV_INPUT_VALIDATED", "expected_calls": len(rows), "silent_skips": 0, "protected_data_accessed": False}, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except T28Error as exc:
        print(f"T28_DEV_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
