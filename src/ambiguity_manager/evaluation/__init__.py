"""Deterministic evaluation package for T24."""

from __future__ import annotations

from ambiguity_manager.evaluation.evaluator import (
    DeterministicEvaluator,
    DuplicatePredictionError,
    evaluate_all_systems,
    evaluate_predictions,
)

__all__ = [
    "DeterministicEvaluator",
    "DuplicatePredictionError",
    "evaluate_all_systems",
    "evaluate_predictions",
]
