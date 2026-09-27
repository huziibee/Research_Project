"""Prospective Figure 6 decision flow, separate from frozen routing policies.

Each gate is supplied by an independently evaluated task representation. This
module does not infer grounding, atomicity, capability, authorization, or risk
from a fluent intent summary. The published figure has binary branches;
``None`` is an explicit experimental extension that abstains to clarification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ambiguity_manager.schema.v2.taxonomies import RouteLabel

GateName = Literal[
    "grounded",
    "one_atomic_action",
    "capable",
    "authorized",
    "risk_acceptable",
]

GATE_ORDER: tuple[GateName, ...] = (
    "grounded",
    "one_atomic_action",
    "capable",
    "authorized",
    "risk_acceptable",
)


@dataclass(frozen=True)
class Fig6GateInput:
    """True/False/unknown judgments, with optional evidence references."""

    grounded: bool | None
    one_atomic_action: bool | None
    capable: bool | None
    authorized: bool | None
    risk_acceptable: bool | None
    evidence: dict[GateName, str] | None = None


@dataclass(frozen=True)
class Fig6GateTrace:
    gate: GateName
    value: bool | None
    evidence: str | None


@dataclass(frozen=True)
class Fig6Decision:
    route: RouteLabel
    first_blocking_gate: GateName | None
    blocking_value: bool | None
    trace: tuple[Fig6GateTrace, ...]


def route_fig6(gates: Fig6GateInput) -> Fig6Decision:
    """Apply the figure's gate order; stop at the first non-true gate.

    The binary branches are literal: failed grounding/atomicity clarify;
    failed capability/authorization/risk refuse. Unknown at *any* gate
    clarifies, an abstention extension not specified by the binary figure.
    """

    trace: list[Fig6GateTrace] = []
    for gate in GATE_ORDER:
        value = getattr(gates, gate)
        if value is not None and type(value) is not bool:
            raise TypeError(f"{gate} must be bool or None")
        evidence = (gates.evidence or {}).get(gate)
        trace.append(Fig6GateTrace(gate, value, evidence))
        if value is None:
            return Fig6Decision(RouteLabel.CLARIFY, gate, None, tuple(trace))
        if value is False:
            route = (
                RouteLabel.CLARIFY
                if gate in ("grounded", "one_atomic_action")
                else RouteLabel.FACE_PRESERVING_REJECTION
            )
            return Fig6Decision(route, gate, False, tuple(trace))
    return Fig6Decision(RouteLabel.EXECUTE, None, None, tuple(trace))
