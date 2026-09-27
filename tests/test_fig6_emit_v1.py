"""Checks that unsupported evidence cannot silently pass a Figure 6 gate."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_fig6_flow_v1 import GATE_ORDER, SCHEMA, validate_output  # noqa: E402


def sample() -> tuple[dict, dict]:
    source = {
        "command": "Move the red case to bay A.",
        "dialogue_history": [],
        "scene_context": "One red case is beside bay A.",
        "capability_context": "The robot can move cases and is authorized in bay A. The path is clear.",
    }
    obj = {
        "intent_summary": "Move the red case to bay A.",
        "cpc": {name: None for name in SCHEMA["properties"]["cpc"]["required"]},
        "unresolved_slots": [],
        "pilot_ambiguity_types": [],
        "alternative_interpretation": None,
        "slot_evidence": [{"slot": "action", "field": "command", "quote": "Move"}],
        "gates": {name: True for name in GATE_ORDER},
        "gate_evidence": {
            name: {"field": "capability_context", "quote": "The robot can move cases"}
            for name in GATE_ORDER
        },
    }
    obj["cpc"]["action"] = "move"
    return source, obj


def test_positive_gate_without_exact_source_quote_abstains() -> None:
    source, obj = sample()
    obj["gate_evidence"]["authorized"] = {"field": "capability_context", "quote": "special approval code"}
    effective, supported, _ = validate_output(obj, source)
    assert effective["authorized"] is None
    assert supported["authorized"] is False


def test_unresolved_material_slot_blocks_grounding() -> None:
    source, obj = sample()
    obj["unresolved_slots"] = ["object"]
    effective, _, _ = validate_output(obj, source)
    assert effective["grounded"] is False


def test_missing_action_cannot_pass_atomicity() -> None:
    source, obj = sample()
    obj["cpc"]["action"] = None
    effective, _, _ = validate_output(obj, source)
    assert effective["one_atomic_action"] is None


def test_unresolved_slot_cannot_also_have_a_value() -> None:
    source, obj = sample()
    obj["unresolved_slots"] = ["action"]
    with pytest.raises(ValueError, match="unresolved_slot_has_value"):
        validate_output(obj, source)


def test_missing_slot_evidence_abstains_from_grounded_execute() -> None:
    source, obj = sample()
    obj["cpc"]["object"] = "red case"
    effective, _, slot_supported = validate_output(obj, source)
    assert effective["grounded"] is None
    assert "object" not in slot_supported


def test_alternative_task_reading_requires_clarification() -> None:
    source, obj = sample()
    obj["alternative_interpretation"] = "Move a different case."
    effective, _, _ = validate_output(obj, source)
    assert effective["grounded"] is False
