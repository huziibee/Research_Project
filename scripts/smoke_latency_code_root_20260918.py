#!/usr/bin/env python3
"""CPU smoke check before GPU latency submit."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_pilot_120_direct_base import verify_freeze  # noqa: E402
from ambiguity_manager.systems.manager import GoalFirstManagerV2  # noqa: E402
from ambiguity_manager.systems.routing import load_route_precedence  # noqa: E402


def main() -> int:
    freeze = verify_freeze(ROOT)
    prec = load_route_precedence()
    GoalFirstManagerV2()
    print("SMOKE_OK", {"n": freeze.get("n"), "precedence_type": type(prec).__name__})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
