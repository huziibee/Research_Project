import json

import pytest

from ambiguity_manager.model.intent_output_contract_v2 import FutureIntentOutputV2, build_future_intent_v2_prompt
from ambiguity_manager.systems.contracts import StructuredAnalysis


def fixture(summary: str, **extra: object) -> str:
    payload = {
        "speech_act": "indirect_request",
        "intent_summary": summary,
        "pilot_ambiguity_types": ["temporal"],
        "pilot_capability_status": "conditional",
        "risk_level": "low",
        "unresolved_slots": ["time"],
        "uncertainty": 0.2,
    }
    payload.update(extra)
    return json.dumps(payload)


def test_future_v2_prompt_fixture_parser_structured_serialization_evaluator_round_trip():
    source = "Could you bring the selected tray after lunch?"
    output = FutureIntentOutputV2.from_model_output(
        fixture("Deliver the selected tray after the relevant lunch service."), source_command=source
    )
    structured = output.to_structured_analysis()
    restored = StructuredAnalysis.from_dict(structured.to_dict())
    assert restored.intent_summary == "Deliver the selected tray after the relevant lunch service."
    assert output.semantic_evaluation_payload()["intent_summary"] == restored.intent_summary
    assert "intent_summary" in build_future_intent_v2_prompt()


@pytest.mark.parametrize("summary", [
    "Do not move the medication cart.",
    "Move the specimen to cold storage only if the temperature check passes.",
    "Move the tray and notify the nurse that it has arrived.",
])
def test_future_v2_preserves_polarity_condition_and_multiple_actions(summary):
    output = FutureIntentOutputV2.from_model_output(fixture(summary), source_command="unrelated wording")
    assert output.intent_summary == summary


def test_future_v2_rejects_command_copy_and_route_language():
    source = "Move the red box to the shelf."
    with pytest.raises(ValueError, match="command_copy"):
        FutureIntentOutputV2.from_model_output(fixture(source), source_command=source)
    with pytest.raises(ValueError, match="route_contamination"):
        FutureIntentOutputV2.from_model_output(fixture("Clarify whether to move the red box."), source_command=source)
