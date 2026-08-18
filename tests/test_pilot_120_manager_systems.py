from __future__ import annotations

from ambiguity_manager.systems.contracts import SystemInput
from scripts.evaluate_pilot_120_manager_systems import (
    TransformerAnalysisProvider,
    normalise_analysis_output,
)


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


def test_invalid_model_analysis_is_retried_once_without_gold(monkeypatch) -> None:
    provider = TransformerAnalysisProvider(
        model=None,
        tokenizer=None,
        max_new_tokens=16,
        retry_max_new_tokens=32,
        constrained_final_max_new_tokens=64,
        provider_id="test",
    )
    prompts: list[tuple[str, int]] = []
    responses = iter(
        [
            '{"speech_act":"directive_command","pilot_ambiguity_types":["invented"]}',
            """{
                "speech_act": "directive_command",
                "pilot_ambiguity_types": ["object_reference"],
                "pilot_capability_status": "capable",
                "risk_level": "low",
                "unresolved_slots": ["object"],
                "uncertainty": 0.5
            }""",
        ]
    )

    def fake_generate(prompt: str, max_new_tokens: int) -> str:
        prompts.append((prompt, max_new_tokens))
        return next(responses)

    monkeypatch.setattr(provider, "_generate", fake_generate)
    analysis = provider.analyse(_input())

    assert analysis is not None
    assert [limit for _, limit in prompts] == [16, 32]
    assert "validation error: unknown_pilot_ambiguity_type" in prompts[1][0]
    assert "Do not infer any hidden gold labels." in prompts[1][0]
    attempts = provider.attempts_by_input_hash[_input().fingerprint()]
    assert [attempt["validation_error"] for attempt in attempts] == ["unknown_pilot_ambiguity_type", None]


def test_schema_constrained_final_emission_follows_two_thinking_failures(monkeypatch) -> None:
    provider = TransformerAnalysisProvider(
        model=None,
        tokenizer=None,
        max_new_tokens=16,
        retry_max_new_tokens=32,
        constrained_final_max_new_tokens=64,
        provider_id="test",
    )
    responses = iter(["not-json", "still-not-json"])
    monkeypatch.setattr(provider, "_generate", lambda *_: next(responses))
    monkeypatch.setattr(
        provider,
        "_generate_constrained",
        lambda _: (
            """{
                "speech_act": "directive_command",
                "pilot_ambiguity_types": [],
                "pilot_capability_status": "capable",
                "risk_level": "none",
                "unresolved_slots": [],
                "uncertainty": 0.0
            }""",
            {"constraint_initialised": True, "transport_status": "constrained_generated"},
        ),
    )

    analysis = provider.analyse(_input())

    assert analysis is not None
    attempts = provider.attempts_by_input_hash[_input().fingerprint()]
    assert [attempt["mode"] for attempt in attempts] == [
        "thinking",
        "thinking_retry",
        "schema_constrained_final_emission_after_two_thinking_attempts",
    ]
    assert attempts[-1]["constraint"]["constraint_initialised"] is True
