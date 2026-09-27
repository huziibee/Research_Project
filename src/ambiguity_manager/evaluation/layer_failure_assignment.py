"""First-observable failure layer. Frozen T39/T41 are not modified."""
from __future__ import annotations

from typing import Literal

Layer = Literal[
    "NONE_ROUTE_CORRECT",
    "Layer_1_semantic_goal_wrong",
    "Layer_2_semantic_goal_correct_speech_act_wrong",
    "Layer_3_goal_and_speech_act_correct_CPC_missing_or_wrong",
    "Layer_4_interpretation_sufficient_router_or_policy_wrong",
]


def assign_first_observable_layer(
    *,
    semantic_goal_correct: bool,
    speech_act_correct: bool,
    cpc_emitted: bool,
    cpc_exact: bool,
    route_correct: bool,
) -> Layer:
    """Assign the first layer at which a route error becomes observable.

    Layer 4 is reachable only when a CPC/resolution frame exists and is exact.
    An empty CPC is Layer 3, not evidence that the router is innocent.
    """
    if route_correct:
        return "NONE_ROUTE_CORRECT"
    if not semantic_goal_correct:
        return "Layer_1_semantic_goal_wrong"
    if not speech_act_correct:
        return "Layer_2_semantic_goal_correct_speech_act_wrong"
    if not cpc_emitted or not cpc_exact:
        return "Layer_3_goal_and_speech_act_correct_CPC_missing_or_wrong"
    return "Layer_4_interpretation_sufficient_router_or_policy_wrong"
