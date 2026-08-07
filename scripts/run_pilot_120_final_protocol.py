#!/usr/bin/env python3
"""Operator entrypoint for Pilot-120 final-protocol workflow."""

from __future__ import annotations

import sys

from ambiguity_manager.evaluation.pilot_120_cli import main


if __name__ == "__main__":
  raise SystemExit(main())
