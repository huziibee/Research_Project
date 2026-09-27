from ambiguity_manager.evaluation.layer_failure_assignment import assign_first_observable_layer
from ambiguity_manager.model.future_task_outcome_contract_v2 import FutureTaskOutcomeV2


def test_layer4_requires_exact_emitted_cpc():
    assert assign_first_observable_layer(
        semantic_goal_correct=True, speech_act_correct=True, cpc_emitted=False, cpc_exact=False, route_correct=False
    ) == "Layer_3_goal_and_speech_act_correct_CPC_missing_or_wrong"
    assert assign_first_observable_layer(
        semantic_goal_correct=True, speech_act_correct=True, cpc_emitted=True, cpc_exact=False, route_correct=False
    ) == "Layer_3_goal_and_speech_act_correct_CPC_missing_or_wrong"
    assert assign_first_observable_layer(
        semantic_goal_correct=True, speech_act_correct=True, cpc_emitted=True, cpc_exact=True, route_correct=False
    ) == "Layer_4_interpretation_sufficient_router_or_policy_wrong"


def test_empty_cpc_cannot_be_called_router_fault():
    layer = assign_first_observable_layer(
        semantic_goal_correct=True, speech_act_correct=True, cpc_emitted=False, cpc_exact=False, route_correct=False
    )
    assert "Layer_4" not in layer


def test_t39_unobserved_outcomes_are_not_task_success():
    outcome = FutureTaskOutcomeV2.unobserved(record_id="CA-0026", predicted_route="clarify", gold_route="execute")
    assert outcome.execution_observed is False
    assert outcome.task_success is None
