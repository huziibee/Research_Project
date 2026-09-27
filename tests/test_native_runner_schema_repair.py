import importlib.util
from pathlib import Path

import pytest


def load(name: str):
    path = Path(__file__).parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


ambik = load("run_ambik_ambiguity_type.py")
native = load("run_native_context_structured.py")


def test_ambik_accepts_extra_fields_and_aliases():
    assert ambik.parse('{"ambiguity_types": ["common_sense"], "rationale": "drawer vs wines"}') == ["commonsense"]
    assert ambik.parse('{"ambiguity_types": ["safety", "preference"]}') == ["preference", "safety_precondition"]
    assert ambik.parse("```json\n{\"ambiguity_types\": [\"commonsense\"]}\n```") == ["commonsense"]


def test_ambik_accepts_source_labels_and_wrapped_items():
    assert ambik.parse('{"ambiguity_types": ["common_sense_knowledge"]}') == ["commonsense"]
    assert ambik.parse('{"ambiguity_type": "preferences"}') == ["preference"]
    assert ambik.parse('{"ambiguity_types": [{"label": "safety"}]}') == ["safety_precondition"]
    assert ambik.parse('["commonsense"]') == ["commonsense"]


def test_ambik_empty_or_unknown_is_abstention_not_gold():
    assert ambik.parse('{"ambiguity_types": []}') == []
    assert ambik.parse('{"ambiguity_types": ["lexical"]}') == []
    with pytest.raises(ValueError, match="ambiguity_types_invalid"):
        ambik.parse('{"ambiguity_types": null}')


def test_indirect_accepts_gold_shaped_empty_types():
    value = native.valid(
        {
            "ambiguity_present": False,
            "ambiguity_types": [],
            "missing_slots": [],
            "note": "extra field from GLM",
        },
        "indirect",
    )
    assert value == {"ambiguity_present": False, "ambiguity_types": [], "missing_slots": []}


def test_indirect_normalizes_none_and_blank_slots():
    value = native.valid(
        {
            "ambiguity_present": "false",
            "ambiguity_types": ["none"],
            "missing_slots": ["", "subtitle preference"],
        },
        "indirect",
    )
    assert value["ambiguity_types"] == []
    assert value["missing_slots"] == ["subtitle preference"]
    assert value["ambiguity_present"] is False


def test_indirect_keeps_pragmatic_contract():
    value = native.valid(
        {"ambiguity_present": True, "ambiguity_types": ["pragmatic"], "missing_slots": ["movie"]},
        "indirect",
    )
    assert value["ambiguity_types"] == ["pragmatic"]


def test_clara_schema_stays_strict():
    with pytest.raises(ValueError, match="schema_invalid"):
        native.valid(
            {
                "ambiguity_present": False,
                "capability_status": "capable",
                "recommended_strategy": "execute",
                "extra": True,
            },
            "clara",
        )
