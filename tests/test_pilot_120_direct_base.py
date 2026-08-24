import pytest

from scripts.evaluate_pilot_120_direct_base import (
    SELECTED_ADAPTER_SYSTEM_ID,
    SYSTEM_ID,
    apply_adapter_scale,
    extract_json,
    normalise_prediction,
    selected_adapter_identity,
)


def test_extract_json_uses_final_object_after_thinking_trace() -> None:
    text = """<think>
Considered this example first: {\"terminal_strategy\": \"clarify\"}.
</think>
{\"terminal_strategy\": \"execute\", \"ambiguity_types\": [\"lexical\"], \"capability_status\": \"capable\"}
"""

    parsed, error = normalise_prediction(extract_json(text))

    assert error is None
    assert parsed == {
        "terminal_strategy": "execute",
        "ambiguity_types": ["lexical"],
        "capability_status": "capable",
    }


def test_extract_json_returns_none_when_no_complete_object_exists() -> None:
    assert extract_json("<think>still reasoning { unfinished") is None


def test_selected_adapter_requires_completed_t28_identity() -> None:
    identity = {
        "selected_adapter": True,
        "adapter_id": "t28-r6-selected",
        "base_model": "Qwen/Qwen3-8B",
        "base_revision": "b968826d9c46dd6066d109eabc6255188de91218",
    }
    assert selected_adapter_identity(identity, adapter_scale=1.0) == "t28-r6-selected"
    with pytest.raises(ValueError, match="requires_selected"):
        selected_adapter_identity(
            {**identity, "selected_adapter": False}, adapter_scale=1.0
        )
    with pytest.raises(ValueError, match="scale_identity_mismatch"):
        selected_adapter_identity(identity, adapter_scale=0.5)


def test_selected_adapter_scale_is_identity_bound() -> None:
    identity = {
        "selected_adapter": True,
        "adapter_id": "t28-r6-selected",
        "adapter_scale": 0.25,
        "base_model": "Qwen/Qwen3-8B",
        "base_revision": "b968826d9c46dd6066d109eabc6255188de91218",
    }
    assert selected_adapter_identity(identity, adapter_scale=0.25) == "t28-r6-selected"


def test_adapter_scale_rejects_nonpositive_value() -> None:
    with pytest.raises(ValueError, match="must_be_positive"):
        apply_adapter_scale(object(), 0.0)


def test_base_and_selected_adapter_system_ids_are_distinct() -> None:
    assert SYSTEM_ID == "direct_base_llm"
    assert SELECTED_ADAPTER_SYSTEM_ID == "t28_selected_adapter_llm"
    assert SYSTEM_ID != SELECTED_ADAPTER_SYSTEM_ID
