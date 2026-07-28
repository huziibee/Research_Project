#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ambiguity_manager.model.t28_trainer import safe_copy_package  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--destination", type=Path, required=True)
    p.add_argument("--identity-json", type=Path, required=True)
    a = p.parse_args()
    identity = json.loads(a.identity_json.read_text(encoding="utf-8"))
    print(json.dumps(safe_copy_package(a.checkpoint, a.destination, identity), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
