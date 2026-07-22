"""Eligibility and denominator reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EligibilityTrace:
  record_id: str
  metric: str
  eligible: bool
  exclusion_reason: str | None = None

  def to_dict(self) -> dict[str, Any]:
    return {
      "record_id": self.record_id,
      "metric": self.metric,
      "eligible": self.eligible,
      "exclusion_reason": self.exclusion_reason,
    }


@dataclass
class MetricReport:
  name: str
  total_records: int
  eligible_records: int
  excluded_records: int
  exclusion_reasons: dict[str, int] = field(default_factory=dict)
  numerator: float | int = 0
  denominator: float | int = 0
  value: float | None = None
  details: dict[str, Any] = field(default_factory=dict)
  eligibility_trace: list[EligibilityTrace] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    return {
      "name": self.name,
      "total_records": self.total_records,
      "eligible_records": self.eligible_records,
      "excluded_records": self.excluded_records,
      "exclusion_reasons": dict(self.exclusion_reasons),
      "numerator": self.numerator,
      "denominator": self.denominator,
      "value": self.value,
      "details": dict(self.details),
      "eligibility_trace": [t.to_dict() for t in self.eligibility_trace],
    }


def safe_div(numerator: float, denominator: float) -> float | None:
  if denominator == 0:
    return None
  return numerator / denominator


def prf(tp: int, fp: int, fn: int) -> dict[str, float | None]:
  precision = safe_div(tp, tp + fp)
  recall = safe_div(tp, tp + fn)
  if precision is None or recall is None or (precision + recall) == 0:
    f1 = None
  else:
    f1 = 2 * precision * recall / (precision + recall)
  return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}
