"""Prospective Figure 6 policy tests; no frozen experiment fixtures."""

import pytest

from ambiguity_manager.schema.v2.taxonomies import RouteLabel
from ambiguity_manager.systems.fig6_flow_v1 import Fig6GateInput, GATE_ORDER, route_fig6


def _gates(**changes: bool | None) -> Fig6GateInput:
    values = dict.fromkeys(GATE_ORDER, True)
    values.update(changes)
    return Fig6GateInput(**values)


@pytest.mark.parametrize(
    ("failed_gate", "expected_route"),
    [
        ("grounded", RouteLabel.CLARIFY),
        ("one_atomic_action", RouteLabel.CLARIFY),
        ("capable", RouteLabel.FACE_PRESERVING_REJECTION),
        ("authorized", RouteLabel.FACE_PRESERVING_REJECTION),
        ("risk_acceptable", RouteLabel.FACE_PRESERVING_REJECTION),
    ],
)
def test_false_branch_stops_at_first_failed_gate(failed_gate, expected_route):
    decision = route_fig6(_gates(**{failed_gate: False}))
    assert decision.route == expected_route
    assert decision.first_blocking_gate == failed_gate
    assert decision.blocking_value is False
    assert tuple(item.gate for item in decision.trace) == GATE_ORDER[: GATE_ORDER.index(failed_gate) + 1]


def test_earlier_gate_has_priority_over_later_failure():
    decision = route_fig6(_gates(grounded=False, capable=False, authorized=False))
    assert decision.route == RouteLabel.CLARIFY
    assert decision.first_blocking_gate == "grounded"
    assert len(decision.trace) == 1


@pytest.mark.parametrize("unknown_gate", GATE_ORDER)
def test_unknown_abstains_to_clarification(unknown_gate):
    decision = route_fig6(_gates(**{unknown_gate: None}))
    assert decision.route == RouteLabel.CLARIFY
    assert decision.first_blocking_gate == unknown_gate
    assert decision.blocking_value is None


def test_all_true_executes_and_preserves_evidence():
    gates = Fig6GateInput(True, True, True, True, True, evidence={"authorized": "approval:123"})
    decision = route_fig6(gates)
    assert decision.route == RouteLabel.EXECUTE
    assert decision.first_blocking_gate is None
    assert tuple(item.gate for item in decision.trace) == GATE_ORDER
    assert decision.trace[3].evidence == "approval:123"


def test_non_boolean_gate_is_rejected():
    with pytest.raises(TypeError, match="capable must be bool or None"):
        route_fig6(_gates(capable="yes"))  # type: ignore[arg-type]
