from __future__ import annotations

from ambiguity_manager.schema.v2.taxonomies import CapabilityStatus, RiskLevel, RouteLabel
from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput
from ambiguity_manager.systems.goal_first_analysis_v2 import (
    ANALYSIS_JSON_SCHEMA,
    build_analysis_prompt,
    normalise_analysis_output,
)
from ambiguity_manager.systems.manager import GoalFirstManagerV2
from ambiguity_manager.systems.routing import (
    DeterministicRouter,
    POLICY_GOAL_FIRST_V2,
    POLICY_GOAL_FIRST_V2_GOAL_LICENSED,
    POLICY_T39_CONSERVATIVE,
)


def _capable_ambiguous() -> StructuredAnalysis:
    return StructuredAnalysis(
        speech_act="directive_command",
        intent_summary="Move the PENDING linen cart to the service alcove at the next idle slot.",
        ambiguity_present=True,
        ambiguity_types=[],
        capability_status=CapabilityStatus.CAPABLE,
        risk_level=RiskLevel.LOW,
        findings=["pilot_capability_status:capable"],
    )


def test_v2_executes_capable_low_risk_despite_ambiguity():
    decision = DeterministicRouter(policy=POLICY_GOAL_FIRST_V2).route(_capable_ambiguous())
    assert decision.recommended_strategy == RouteLabel.EXECUTE
    assert decision.matched_rule_id == "context_licensed_execute"


def test_v2_executes_conditional_low_risk():
    analysis = _capable_ambiguous()
    analysis.capability_status = CapabilityStatus.CONDITIONAL
    analysis.findings = ["pilot_capability_status:conditionally_capable"]
    decision = DeterministicRouter(policy=POLICY_GOAL_FIRST_V2).route(analysis)
    assert decision.recommended_strategy == RouteLabel.EXECUTE


def test_v2_asks_unauthorised_at_low_risk_instead_of_refusing():
    """Low-risk unauthorized bits must not hard-refuse (Pilot-120 autopsy)."""
    analysis = _capable_ambiguous()
    analysis.capability_status = CapabilityStatus.UNKNOWN
    analysis.risk_level = RiskLevel.LOW
    analysis.findings = ["pilot_capability_status:unauthorized"]
    decision = DeterministicRouter(policy=POLICY_GOAL_FIRST_V2).route(analysis)
    assert decision.recommended_strategy == RouteLabel.CLARIFY
    assert decision.matched_rule_id == "default_clarify"


def test_v2_refuses_unauthorised_at_elevated_risk():
    analysis = _capable_ambiguous()
    analysis.capability_status = CapabilityStatus.UNKNOWN
    analysis.risk_level = RiskLevel.MEDIUM
    analysis.findings = ["pilot_capability_status:unauthorized"]
    decision = DeterministicRouter(policy=POLICY_GOAL_FIRST_V2).route(analysis)
    assert decision.recommended_strategy == RouteLabel.FACE_PRESERVING_REJECTION
    assert decision.matched_rule_id == "known_unsafe_or_prohibited"


def test_v2_still_rejects_incapable():
    analysis = _capable_ambiguous()
    analysis.capability_status = CapabilityStatus.INCAPABLE
    decision = DeterministicRouter(policy=POLICY_GOAL_FIRST_V2).route(analysis)
    assert decision.recommended_strategy == RouteLabel.FACE_PRESERVING_REJECTION


def test_v2_still_asks_when_speech_act_is_a_question():
    analysis = _capable_ambiguous()
    analysis.speech_act = "information_question"
    analysis.intent_summary = "Move the PENDING linen cart to the service alcove."
    decision = DeterministicRouter(policy=POLICY_GOAL_FIRST_V2).route(analysis)
    assert decision.recommended_strategy == RouteLabel.CLARIFY


def test_goal_licensed_executes_polite_question_when_summary_is_a_job():
    analysis = _capable_ambiguous()
    analysis.speech_act = "information_question"
    analysis.intent_summary = "Move the PENDING linen cart to the service alcove."
    decision = DeterministicRouter(policy=POLICY_GOAL_FIRST_V2_GOAL_LICENSED).route(analysis)
    assert decision.recommended_strategy == RouteLabel.EXECUTE
    assert "goal_licensed_despite_question_shaped_speech_act" in decision.notes


def test_goal_licensed_still_asks_when_summary_is_a_real_question():
    analysis = _capable_ambiguous()
    analysis.speech_act = "information_question"
    analysis.intent_summary = "What time is the next idle slot?"
    decision = DeterministicRouter(policy=POLICY_GOAL_FIRST_V2_GOAL_LICENSED).route(analysis)
    assert decision.recommended_strategy == RouteLabel.CLARIFY

def test_conservative_policy_unchanged():
    decision = DeterministicRouter(policy=POLICY_T39_CONSERVATIVE).route(_capable_ambiguous())
    assert decision.recommended_strategy == RouteLabel.CLARIFY


def test_v2_prompt_asks_for_intent_and_cpc_before_unresolved():
    prompt = build_analysis_prompt(
        SystemInput(record_id="CA-0007", command="Move the cart.", scene_context="Two carts.")
    )
    assert prompt.index("intent_summary") < prompt.index("unresolved_slots")
    assert "cpc" in prompt
    assert "Do not choose a final route" in prompt


def test_extract_analysis_json_prefers_intent_summary_over_trailing_fragment():
    from ambiguity_manager.systems.goal_first_analysis_v2 import extract_analysis_json

    raw = (
        '<think>notes</think>\n'
        '{"intent_summary":"Move the cart.","speech_act":"directive_command",'
        '"cpc":{},"pilot_ambiguity_types":[],"pilot_capability_status":"capable",'
        '"risk_level":"low","unresolved_slots":[],"uncertainty":0.1}\n'
        '{"status":"unknown","value":"one"}'
    )
    obj = extract_analysis_json(raw)
    assert obj is not None
    assert obj["intent_summary"] == "Move the cart."

    payload = {
        "intent_summary": "Deliver the pending medicine tray after the 11:00 meal service.",
        "speech_act": "indirect_request",
        "cpc": {
            name: {"status": "unknown", "value": None}
            for name in ANALYSIS_JSON_SCHEMA["properties"]["cpc"]["required"]
        },
        "pilot_ambiguity_types": ["temporal_reference"],
        "pilot_capability_status": "capable",
        "risk_level": "low",
        "unresolved_slots": ["time", "destination"],
        "uncertainty": 0.4,
    }
    payload["cpc"]["action"] = {"status": "filled", "value": "deliver"}
    payload["cpc"]["object"] = {"status": "filled", "value": "pending medicine tray"}
    payload["cpc"]["time"] = {"status": "filled", "value": "11:00 meal service"}
    system_input = SystemInput(
        record_id="CA-0007",
        command="Can the selected controlled medicine tray be delivered after a scheduled meal service?",
        scene_context="Current time is 10:39. Meal service is scheduled at 11:00. Assigned destination is ward bay.",
        dialogue_history=("nurse: treat that as a request",),
    )
    analysis, meta, error = normalise_analysis_output(
        payload, system_input=system_input, provider_id="test"
    )
    assert error is None
    assert analysis is not None
    assert analysis.intent_summary.startswith("Deliver the pending")
    assert analysis.cpc.action.value == "deliver"
    assert "time" not in (meta or {})["unresolved_slots_after_licence"]
    assert "destination" not in (meta or {})["unresolved_slots_after_licence"]


def test_v2_manager_executes_with_remaining_unresolved_slots():
    from ambiguity_manager.schema.v2.records import UnresolvedSlot

    analysis = _capable_ambiguous()
    analysis.unresolved_slots = [UnresolvedSlot(slot_name="destination", reason="model_identified_uncertainty")]
    result = GoalFirstManagerV2().run(
        SystemInput(record_id="CA-TEST", command="Move the marked cart."),
        cached_analysis=analysis,
    )
    assert result.recommended_strategy == RouteLabel.EXECUTE
    assert result.execution_status == "ok"


def test_v2_normaliser_rejects_command_copy_summary():
    command = "Move the cart to the alcove."
    payload = {
        "intent_summary": command,
        "speech_act": "directive_command",
        "cpc": {
            name: {"status": "unknown", "value": None}
            for name in ANALYSIS_JSON_SCHEMA["properties"]["cpc"]["required"]
        },
        "pilot_ambiguity_types": [],
        "pilot_capability_status": "capable",
        "risk_level": "low",
        "unresolved_slots": [],
        "uncertainty": 0.1,
    }
    analysis, meta, error = normalise_analysis_output(
        payload,
        system_input=SystemInput(record_id="CA-TEST", command=command),
        provider_id="test",
    )
    assert analysis is None and meta is None
    assert error == "intent_summary_copied_command"
