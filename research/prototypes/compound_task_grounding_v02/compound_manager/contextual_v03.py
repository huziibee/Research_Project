"""Optional contextual-choice preflight for the Qwen TaskSpec pipeline.

Derives incomplete, evidence-linked hints solely from raw utterance/scene/dialogue.
Does not use gold labels, case IDs, prior routes, capability, permission or risk.
It is a development assist, not proof of candidate coverage or generalization.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .model_adapter import build_model_prompt
from .pipeline import LanguageModel, run_first_turn
from .source_probe_v03 import probe, PROBE_VERSION

CONTEXTUAL_PROMPT_VERSION = "compound_task_contextual_v0.3"


def contextual_alerts(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Do not turn heuristic evidence into oracle ground truth."""
    hints = []
    for item in probe(source)["evidence"]:
        if item.get("target") is None:
            continue
        hints.append({
            "target": item["target"],
            "source_field": item["source"],
            "verbatim_source_evidence": item["quote"],
            "potential_alternatives": item["candidates"],
            "proposed_question": item["question"],
            "verified_as_complete": False,
        })
    return hints


def contextual_prompt(source: dict[str, Any]) -> str:
    """Prompt constructed from source only; frozen gold is never loaded."""
    return add_alerts_to_prompt(build_model_prompt(source), source)


def add_alerts_to_prompt(base_prompt: str, source: dict[str, Any]) -> str:
    hints = contextual_alerts(source)
    return (
        base_prompt
        + "\nCONTEXTUAL_CHOICE_PREFLIGHT_VERSION=" + CONTEXTUAL_PROMPT_VERSION
        + "\nSOURCE_ONLY_ALERTS_JSON=" + json.dumps(hints, ensure_ascii=False, sort_keys=True)
        + "\nThe alerts are unverified suggestions from the supplied scene, not gold labels. "
          "Check each against the source and identify any other competing interpretations. "
          "In particular, a singular selected item may have several pending candidates; "
          "a recipient role may designate multiple people; a destination may have multiple "
          "valid units without a selected identifier; or a measuring tool may depend on an "
          "unstated range. Preserve genuine alternatives as options with grounded=null. "
          "Do not assume an empty list of alerts proves the task is grounded. "
          "Resolve only through evidence, not by guessing."
    )


@dataclass
class ContextualizedModel:
    """Decorator for any inference model implementing LanguageModel.generate."""
    delegate: LanguageModel

    def generate(self, prompt: str, source: dict[str, Any]) -> str:
        return self.delegate.generate(add_alerts_to_prompt(prompt, source), source)


def run_contextual_first_turn(source: dict[str, Any], model: LanguageModel,
                              *, strict_evidence: bool = True) -> dict[str, Any]:
    """Run TaskSpec decoding, then detect unjustified source/graph disagreement.

    If text evidence indicates competing decisions while the generated graph
    has only one ready task, do not make a positive readiness claim. Instead
    request another interpretation / better scene representation. This is
    *not* a synthesized user clarification or a successful resolved graph.
    """
    hints = contextual_alerts(source)
    state = run_first_turn(source, ContextualizedModel(model),
                           strict_evidence=strict_evidence)
    state["source_only_context_alerts"] = hints
    state["contextual_prompt_version"] = CONTEXTUAL_PROMPT_VERSION
    state["contextual_probe_version"] = PROBE_VERSION
    state["contextual_coverage_verified"] = False
    if hints and state["status"] == "action_ready":
        state["status"] = "needs_context_repair"
        state["verdict"] = {
            "record_id": source.get("record_id"),
            "status": "needs_context_repair",
            "action_ready": False,
            "reason": "source_candidate_multiplicity_not_represented_in_ready_task",
            "unresolved_source_hints": [h["target"] for h in hints],
        }
        state["readiness_blocked_by_context_audit"] = True
    else:
        state["readiness_blocked_by_context_audit"] = False
    return state