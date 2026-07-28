#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ambiguity_manager.model.t28 import choose_checkpoint  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--eligibility", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    data = json.loads(a.eligibility.read_text(encoding="utf-8"))
    selected = choose_checkpoint(data["checkpoints"])
    result = {"policy": "configs/model/t28_frozen_selection_policy_v1.json", "selected": selected, "ranking": sorted([c for c in data["checkpoints"] if c.get("eligible")], key=lambda c: (-float(c.get("primary", 0)), -float(c.get("schema_validity", 0)), -float(c.get("safety_margin", 0)), int(c.get("repair_count", 0)), int(c.get("step", 0)), str(c.get("checkpoint_id", c.get("checkpoint", ""))))) }
    a.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
