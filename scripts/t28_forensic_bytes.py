#!/usr/bin/env python3
"""Binary-only forensic comparison for frozen T28 inputs and archive stages."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ambiguity_manager.model.t28_bundle import binary_stats, first_difference

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--source", type=Path, required=True); p.add_argument("--stage", action="append", nargs=2, metavar=("LABEL", "PATH"), required=True); p.add_argument("--output", type=Path, required=True); args = p.parse_args()
    source = args.source.read_bytes(); result = {"source": binary_stats(args.source), "stages": []}
    for label, raw in args.stage:
        path = Path(raw); data = path.read_bytes(); result["stages"].append({"label": label, "stats": binary_stats(path), "matches_source": data == source, "first_difference": first_difference(source, data)})
    args.output.write_bytes((json.dumps(result, sort_keys=True, indent=2) + "\n").encode("utf-8")); print(json.dumps(result, sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
