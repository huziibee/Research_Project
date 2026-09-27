"""Prospective task-outcome contract; never inferred from frozen T39 routes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_ALLOWED_SUCCESS = frozenset({True, False, None})


@dataclass(frozen=True)
class FutureTaskOutcomeV2:
    record_id: str
    predicted_route: str
    gold_route: str | None
    intent_summary: str | None
    execution_observed: bool
    task_success: bool | None
    safety_violation: bool | None
    partial_completion: bool | None
    claim_boundary: str

    @classmethod
    def unobserved(cls, *, record_id: str, predicted_route: str, gold_route: str | None = None, intent_summary: str | None = None) -> "FutureTaskOutcomeV2":
        """Placeholder when no environment executed the action."""
        return cls(
            record_id=record_id,
            predicted_route=predicted_route,
            gold_route=gold_route,
            intent_summary=intent_summary,
            execution_observed=False,
            task_success=None,
            safety_violation=None,
            partial_completion=None,
            claim_boundary="task success NOT_COMPUTED; route correctness is not environment success",
        )

    @classmethod
    def from_observed_execution(
        cls,
        *,
        record_id: str,
        predicted_route: str,
        gold_route: str | None,
        intent_summary: str | None,
        task_success: bool,
        safety_violation: bool,
        partial_completion: bool,
    ) -> "FutureTaskOutcomeV2":
        if any(value not in _ALLOWED_SUCCESS or value is None for value in (task_success, safety_violation, partial_completion)):
            raise ValueError("future_outcome_v2_observed_fields_must_be_boolean")
        return cls(
            record_id=record_id,
            predicted_route=predicted_route,
            gold_route=gold_route,
            intent_summary=intent_summary,
            execution_observed=True,
            task_success=task_success,
            safety_violation=safety_violation,
            partial_completion=partial_completion,
            claim_boundary="environment-observed task outcome; independent of speech-act and route labels",
        )

    @classmethod
    def from_route_correctness(cls, *args: Any, **kwargs: Any) -> "FutureTaskOutcomeV2":
        raise ValueError("cannot_infer_task_success_from_route")

    def accidental_route_correctness_is_not_task_success(self) -> bool:
        return self.task_success is None or self.execution_observed is True

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "predicted_route": self.predicted_route,
            "gold_route": self.gold_route,
            "intent_summary": self.intent_summary,
            "execution_observed": self.execution_observed,
            "task_success": self.task_success,
            "safety_violation": self.safety_violation,
            "partial_completion": self.partial_completion,
            "claim_boundary": self.claim_boundary,
        }
