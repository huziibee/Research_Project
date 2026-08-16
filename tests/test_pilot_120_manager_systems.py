from __future__ import annotations

from ambiguity_manager.systems.contracts import SystemInput
from scripts.evaluate_pilot_120_manager_systems import normalise_analysis_output


def _input() -> SystemInput:
    return SystemInput(record_id="p120-test", command="Move it there.")


def test_normalise_manager_analysis_preserves_pilot_labels_without_gold() -> None:
    analysis, metadata, error = normalise_analysis_output(
        {
            "speech_act": "directive_command",
            "pilot_ambiguity_types": ["object_reference", "temporal_reference"],
            "pilot_capability_status": "capable",
            "risk_level": "low",
            "unresolved_slots": ["object", "time"],
            "uncertainty": 0.7,
        },
        system_input=_input(),
        provider_id="test",
    )
    assert error is None
    assert metadata == {
        "pilot_ambiguity_types": ["object_reference", "temporal_reference"],
        "pilot_capability_status": "capable",
    }
    assert analysis is not None
    assert {item.value for item in analysis.ambiguity_types} == {"referential", "temporal"}
    assert [slot.slot_name for slot in analysis.unresolved_slots] == ["object", "time"]


def test_normalise_manager_analysis_rejects_unknown_label() -> None:
    analysis, metadata, error = normalise_analysis_output(
        {
            "speech_act": "directive_command",
            "pilot_ambiguity_types": ["invented"],
            "pilot_capability_status": "capable",
            "risk_level": "none",
            "unresolved_slots": [],
            "uncertainty": 0,
        },
        system_input=_input(),
        provider_id="test",
    )
    assert analysis is None
    assert metadata is None
    assert error == "unknown_pilot_ambiguity_type"
