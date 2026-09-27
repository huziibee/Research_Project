"""Prospective V2 intent-output contract; never used by frozen T39."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ambiguity_manager.model.parser import extract_and_repair_json
from ambiguity_manager.systems.contracts import StructuredAnalysis

_ROUTE_TERMS = re.compile(r"\b(execute|clarify|reject|route|silently resolve)\b", re.I)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def build_future_intent_v2_prompt() -> str:
    """Prompt fragment for a separately versioned future manager only."""
    return (
        "Return one JSON object with speech_act, intent_summary, "
        "pilot_ambiguity_types, pilot_capability_status, risk_level, "
        "unresolved_slots, and uncertainty. intent_summary must state the "
        "user's top-level goal, preserve polarity and all required actions, "
        "paraphrase rather than copy the command, and must not choose a route."
    )


@dataclass(frozen=True)
class FutureIntentOutputV2:
    speech_act: str
    intent_summary: str
    pilot_ambiguity_types: tuple[str, ...]
    pilot_capability_status: str
    risk_level: str
    unresolved_slots: tuple[str, ...]
    uncertainty: float

    @classmethod
    def from_model_output(cls, raw_output: str, *, source_command: str) -> "FutureIntentOutputV2":
        parsed = extract_and_repair_json(raw_output).parsed_object
        if not isinstance(parsed, dict):
            raise ValueError("future_intent_v2_not_json_object")
        required = {"speech_act", "intent_summary", "pilot_ambiguity_types", "pilot_capability_status", "risk_level", "unresolved_slots", "uncertainty"}
        if set(parsed) != required:
            raise ValueError("future_intent_v2_fields_mismatch")
        summary = parsed["intent_summary"]
        if not isinstance(summary, str) or not summary.strip() or len(summary.strip()) > 500:
            raise ValueError("future_intent_v2_invalid_summary")
        if _normalise(summary) == _normalise(source_command):
            raise ValueError("future_intent_v2_command_copy")
        if _ROUTE_TERMS.search(summary):
            raise ValueError("future_intent_v2_route_contamination")
        if not isinstance(parsed["speech_act"], str):
            raise ValueError("future_intent_v2_invalid_speech_act")
        if not isinstance(parsed["pilot_ambiguity_types"], list) or not all(isinstance(v, str) for v in parsed["pilot_ambiguity_types"]):
            raise ValueError("future_intent_v2_invalid_ambiguity_types")
        if not isinstance(parsed["unresolved_slots"], list) or not all(isinstance(v, str) for v in parsed["unresolved_slots"]):
            raise ValueError("future_intent_v2_invalid_unresolved_slots")
        if not isinstance(parsed["pilot_capability_status"], str) or not isinstance(parsed["risk_level"], str):
            raise ValueError("future_intent_v2_invalid_status")
        if not isinstance(parsed["uncertainty"], (int, float)) or not 0 <= parsed["uncertainty"] <= 1:
            raise ValueError("future_intent_v2_invalid_uncertainty")
        return cls(parsed["speech_act"], summary.strip(), tuple(parsed["pilot_ambiguity_types"]), parsed["pilot_capability_status"], parsed["risk_level"], tuple(parsed["unresolved_slots"]), float(parsed["uncertainty"]))

    def to_structured_analysis(self) -> StructuredAnalysis:
        return StructuredAnalysis.from_dict({"speech_act": self.speech_act, "intent_summary": self.intent_summary})

    def semantic_evaluation_payload(self) -> dict[str, Any]:
        """The route-free future field supplied to the five-check SGC evaluator."""
        return {"intent_summary": self.intent_summary, "speech_act": self.speech_act}
