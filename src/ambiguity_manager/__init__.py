"""Risk-Aware Ambiguity Manager package.

Scaffold established in ticket T00. This package evaluates the natural-language
coordination layer for ambiguous robot/user commands. It does not implement
robot planning, execution, navigation, grasping, or a full embodied safety
system.

Canonical schema (T01) and later converters, models, routing, and evaluation
logic live in subpackages. This module exposes version metadata at the root.
"""

from __future__ import annotations

__version__ = "0.0.0"

__all__ = ["__version__"]
