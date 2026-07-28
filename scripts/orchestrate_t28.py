#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ambiguity_manager.model.t28_trainer import T28RunOrchestrator  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--matrix", type=Path, required=True)
    p.add_argument("--output-root", type=Path, required=True)
    p.add_argument("--prepare-only", action="store_true")
    args = p.parse_args()
    orch = T28RunOrchestrator(args.matrix, args.output_root)
    prepared = [str(orch.prepare_run_directory(run_id)) for run_id in orch.run_ids()]
    print(json.dumps({"status": "PREPARED", "sequential": True, "run_ids": orch.run_ids(), "directories": prepared}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
