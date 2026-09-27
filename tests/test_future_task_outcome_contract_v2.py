import json
from pathlib import Path

import pytest

from ambiguity_manager.model.future_task_outcome_contract_v2 import FutureTaskOutcomeV2


def test_unobserved_outcome_does_not_claim_task_success():
    outcome = FutureTaskOutcomeV2.unobserved(record_id="CA-0007", predicted_route="clarify", gold_route="execute")
    payload = outcome.to_dict()
    assert payload["execution_observed"] is False
    assert payload["task_success"] is None
    assert "NOT_COMPUTED" in payload["claim_boundary"]


def test_observed_success_is_independent_of_wrong_route():
    outcome = FutureTaskOutcomeV2.from_observed_execution(
        record_id="CA-0007",
        predicted_route="clarify",
        gold_route="execute",
        intent_summary="Deliver the selected tray after lunch.",
        task_success=True,
        safety_violation=False,
        partial_completion=False,
    )
    assert outcome.task_success is True
    assert outcome.predicted_route != outcome.gold_route


def test_route_correctness_cannot_mint_task_success():
    with pytest.raises(ValueError, match="cannot_infer_task_success_from_route"):
        FutureTaskOutcomeV2.from_route_correctness(record_id="CA-0007", route_correct=True)
