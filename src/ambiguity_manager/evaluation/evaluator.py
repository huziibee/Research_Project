"""Deterministic interpretation and routing evaluator."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ambiguity_manager.evaluation.eligibility import MetricReport, EligibilityTrace, prf, safe_div
from ambiguity_manager.evaluation.normalisation import load_cpc_normalisation, normalise_text
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES
from ambiguity_manager.systems.candidate_generation import candidate_set_fingerprint
from ambiguity_manager.systems.hashing import sha256_json


def load_evaluator_policy(path: Path | None = None) -> dict[str, Any]:
  if path is None:
    path = ProjectPaths.from_repo_root().configs / "evaluation" / "evaluator_policy_v1.json"
  return json.loads(path.read_text(encoding="utf-8"))


def _get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
  cur: Any = d
  for key in keys:
    if not isinstance(cur, dict) or key not in cur:
      return default
    cur = cur[key]
  return cur


def _as_set(values: list[Any] | None) -> set[str]:
  return {str(v) for v in (values or [])}


@dataclass
class GoldRecord:
  record_id: str
  payload: dict[str, Any]

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "GoldRecord":
    rid = data.get("record_id") or data.get("id")
    if not rid:
      raise ValueError("gold record missing record_id")
    return cls(record_id=str(rid), payload=data)


@dataclass
class PredictionRecord:
  record_id: str
  system_id: str
  payload: dict[str, Any]
  execution_status: str = "ok"

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "PredictionRecord":
    rid = data.get("record_id")
    sid = data.get("system_id", "unknown")
    if not rid:
      raise ValueError("prediction missing record_id")
    return cls(
      record_id=str(rid),
      system_id=str(sid),
      payload=data,
      execution_status=str(data.get("execution_status", "ok")),
    )


@dataclass
class EvaluationBundle:
  metrics: dict[str, MetricReport] = field(default_factory=dict)
  evaluator_version: str = "t24-deterministic-1.0.0"
  synthetic_only: bool = True
  official_result: bool = False

  def to_dict(self) -> dict[str, Any]:
    return {
      "evaluator_version": self.evaluator_version,
      "synthetic_only": self.synthetic_only,
      "official_result": self.official_result,
      "metrics": {k: v.to_dict() for k, v in self.metrics.items()},
      "bundle_hash": sha256_json(
        {
          "evaluator_version": self.evaluator_version,
          "metrics": {k: v.to_dict() for k, v in self.metrics.items()},
        }
      ),
    }


class DeterministicEvaluator:
  def __init__(self, policy: dict[str, Any] | None = None, norm: dict[str, Any] | None = None) -> None:
    self.policy = policy or load_evaluator_policy()
    self.norm = norm or load_cpc_normalisation()
    self.evaluator_version = str(self.policy.get("evaluator_version", "t24-deterministic-1.0.0"))
    self.critical_slots = list(self.norm.get("critical_slots", []))

  def evaluate(
    self,
    gold_records: list[GoldRecord],
    predictions: list[PredictionRecord],
    *,
    system_id: str | None = None,
  ) -> EvaluationBundle:
    gold_by_id = {g.record_id: g for g in gold_records}
    preds = [p for p in predictions if system_id is None or p.system_id == system_id]
    pred_by_id: dict[str, PredictionRecord] = {}
    for p in preds:
      # last wins but duplicates tracked in details where needed
      pred_by_id[p.record_id] = p

    metrics: dict[str, MetricReport] = {}
    metrics["intent_accuracy"] = self._intent_accuracy(gold_by_id, pred_by_id)
    metrics.update(self._cpc_metrics(gold_by_id, pred_by_id))
    metrics.update(self._candidate_metrics(gold_by_id, pred_by_id))
    metrics.update(self._ambiguity_metrics(gold_by_id, pred_by_id))
    metrics["risk_accuracy"] = self._label_accuracy(
      gold_by_id, pred_by_id, "risk_accuracy", "risk_level", ("analysis", "risk_level"), "risk"
    )
    metrics["capability_accuracy"] = self._label_accuracy(
      gold_by_id,
      pred_by_id,
      "capability_accuracy",
      "capability_status",
      ("analysis", "capability_status"),
      "capability",
    )
    metrics.update(self._routing_metrics(gold_by_id, pred_by_id))
    metrics.update(self._safety_metrics(gold_by_id, pred_by_id))
    metrics.update(self._response_structural_metrics(gold_by_id, pred_by_id))
    return EvaluationBundle(
      metrics=metrics,
      evaluator_version=self.evaluator_version,
      synthetic_only=True,
      official_result=False,
    )

  def _eligible(
    self,
    gold: GoldRecord,
    pred: PredictionRecord | None,
    metric: str,
    eligibility_field: str | None,
  ) -> tuple[bool, str | None]:
    elig = gold.payload.get("label_eligibility") or gold.payload.get("eligibility") or {}
    if eligibility_field and isinstance(elig, dict) and eligibility_field in elig:
      if not elig[eligibility_field]:
        return False, f"ineligible_{eligibility_field}"
    if metric.startswith("intent") and gold.payload.get("speech_act") is None and gold.payload.get("gold_intent") is None:
      return False, "missing_gold"
    if pred is None:
      return False, "missing_prediction"
    if pred.execution_status in {"provider_unavailable", "not_executable"}:
      return False, "not_executable"
    return True, None

  def _intent_accuracy(
    self,
    gold_by_id: dict[str, GoldRecord],
    pred_by_id: dict[str, PredictionRecord],
  ) -> MetricReport:
    total = len(gold_by_id)
    correct = 0
    eligible = 0
    excluded = 0
    reasons: Counter[str] = Counter()
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    support: Counter[str] = Counter()
    trace: list[EligibilityTrace] = []
    for rid, gold in gold_by_id.items():
      pred = pred_by_id.get(rid)
      ok, reason = self._eligible(gold, pred, "intent", "intent_slots")
      gold_intent = gold.payload.get("gold_intent") or gold.payload.get("speech_act")
      if gold_intent is None:
        ok, reason = False, "missing_gold"
      trace.append(EligibilityTrace(rid, "intent_accuracy", ok, reason))
      if not ok:
        excluded += 1
        reasons[reason or "excluded"] += 1
        continue
      eligible += 1
      assert pred is not None
      pred_intent = _get(pred.payload, "analysis", "speech_act") or pred.payload.get("speech_act")
      support[str(gold_intent)] += 1
      confusion[str(gold_intent)][str(pred_intent)] += 1
      if pred_intent == gold_intent:
        correct += 1
    return MetricReport(
      name="intent_accuracy",
      total_records=total,
      eligible_records=eligible,
      excluded_records=excluded,
      exclusion_reasons=dict(reasons),
      numerator=correct,
      denominator=eligible,
      value=safe_div(correct, eligible),
      details={
        "per_intent_support": dict(support),
        "confusion_matrix": {k: dict(v) for k, v in confusion.items()},
      },
      eligibility_trace=trace,
    )

  def _cpc_metrics(
    self,
    gold_by_id: dict[str, GoldRecord],
    pred_by_id: dict[str, PredictionRecord],
  ) -> dict[str, MetricReport]:
    total = len(gold_by_id)
    tp = fp = fn = 0
    exact_num = exact_den = 0
    critical_num = critical_den = 0
    joint_num = joint_den = 0
    per_slot_correct: Counter[str] = Counter()
    per_slot_total: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    eligible = excluded = 0
    traces: list[EligibilityTrace] = []
    rules = self.norm.get("rules", {})

    for rid, gold in gold_by_id.items():
      pred = pred_by_id.get(rid)
      ok, reason = self._eligible(gold, pred, "cpc", "intent_slots")
      gold_cpc = gold.payload.get("gold_cpc") or gold.payload.get("cpc")
      if not isinstance(gold_cpc, dict):
        ok, reason = False, "missing_gold"
      traces.append(EligibilityTrace(rid, "cpc", ok, reason))
      if not ok:
        excluded += 1
        reasons[reason or "excluded"] += 1
        continue
      eligible += 1
      assert pred is not None
      pred_cpc = _get(pred.payload, "analysis", "cpc") or pred.payload.get("cpc") or {}
      gold_filled: dict[str, str] = {}
      pred_filled: dict[str, str] = {}
      for slot in CPC_SLOT_NAMES:
        gslot = gold_cpc.get(slot, {})
        if isinstance(gslot, dict):
          gval = gslot.get("value")
          gstatus = gslot.get("status")
        else:
          gval, gstatus = gslot, "filled" if gslot else "missing"
        if gstatus == "filled" and gval is not None:
          gold_filled[slot] = normalise_text(str(gval), rules) or ""
        pslot = pred_cpc.get(slot, {}) if isinstance(pred_cpc, dict) else {}
        if isinstance(pslot, dict):
          pval = pslot.get("value")
          pstatus = pslot.get("status")
        else:
          pval, pstatus = pslot, "filled" if pslot else "missing"
        if pstatus == "filled" and pval is not None:
          pred_filled[slot] = normalise_text(str(pval), rules) or ""

      for slot, gval in gold_filled.items():
        per_slot_total[slot] += 1
        pval = pred_filled.get(slot)
        if pval == gval:
          tp += 1
          per_slot_correct[slot] += 1
        else:
          fn += 1
      for slot, pval in pred_filled.items():
        if slot not in gold_filled:
          fp += 1

      exact_den += 1
      if gold_filled == pred_filled:
        exact_num += 1

      crit_ok = True
      for slot in self.critical_slots:
        if slot in gold_filled:
          critical_den += 1
          if pred_filled.get(slot) == gold_filled[slot]:
            critical_num += 1
          else:
            crit_ok = False
        elif slot in pred_filled:
          crit_ok = False

      gold_intent = gold.payload.get("gold_intent") or gold.payload.get("speech_act")
      pred_intent = _get(pred.payload, "analysis", "speech_act")
      joint_den += 1
      if gold_intent == pred_intent and gold_filled == pred_filled:
        joint_num += 1

    slot_prf = prf(tp, fp, fn)
    return {
      "cpc_slot_precision": MetricReport(
        name="cpc_slot_precision",
        total_records=total,
        eligible_records=eligible,
        excluded_records=excluded,
        exclusion_reasons=dict(reasons),
        numerator=tp,
        denominator=tp + fp,
        value=slot_prf["precision"],
        details=slot_prf,
        eligibility_trace=traces,
      ),
      "cpc_slot_recall": MetricReport(
        name="cpc_slot_recall",
        total_records=total,
        eligible_records=eligible,
        excluded_records=excluded,
        exclusion_reasons=dict(reasons),
        numerator=tp,
        denominator=tp + fn,
        value=slot_prf["recall"],
        details=slot_prf,
        eligibility_trace=traces,
      ),
      "cpc_slot_f1": MetricReport(
        name="cpc_slot_f1",
        total_records=total,
        eligible_records=eligible,
        excluded_records=excluded,
        exclusion_reasons=dict(reasons),
        numerator=slot_prf["f1"] or 0,
        denominator=1 if slot_prf["f1"] is not None else 0,
        value=slot_prf["f1"],
        details={**slot_prf, "per_slot_accuracy": {
          s: safe_div(per_slot_correct[s], per_slot_total[s]) for s in per_slot_total
        }},
        eligibility_trace=traces,
      ),
      "cpc_exact_match": MetricReport(
        name="cpc_exact_match",
        total_records=total,
        eligible_records=eligible,
        excluded_records=excluded,
        exclusion_reasons=dict(reasons),
        numerator=exact_num,
        denominator=exact_den,
        value=safe_div(exact_num, exact_den),
        eligibility_trace=traces,
      ),
      "critical_slot_accuracy": MetricReport(
        name="critical_slot_accuracy",
        total_records=total,
        eligible_records=eligible,
        excluded_records=excluded,
        exclusion_reasons=dict(reasons),
        numerator=critical_num,
        denominator=critical_den,
        value=safe_div(critical_num, critical_den),
        eligibility_trace=traces,
      ),
      "joint_intent_cpc": MetricReport(
        name="joint_intent_cpc",
        total_records=total,
        eligible_records=eligible,
        excluded_records=excluded,
        exclusion_reasons=dict(reasons),
        numerator=joint_num,
        denominator=joint_den,
        value=safe_div(joint_num, joint_den),
        eligibility_trace=traces,
      ),
    }

  def _candidate_metrics(
    self,
    gold_by_id: dict[str, GoldRecord],
    pred_by_id: dict[str, PredictionRecord],
  ) -> dict[str, MetricReport]:
    total = len(gold_by_id)
    tp = fp = fn = 0
    exact_num = exact_den = 0
    selected_num = selected_den = 0
    unsupported_num = unsupported_den = 0
    reasons: Counter[str] = Counter()
    eligible = excluded = 0
    traces: list[EligibilityTrace] = []

    for rid, gold in gold_by_id.items():
      pred = pred_by_id.get(rid)
      ok, reason = self._eligible(gold, pred, "candidates", "intent_slots")
      gold_cands = gold.payload.get("gold_candidate_ids") or [
        c.get("frame_id") for c in gold.payload.get("candidate_interpretations", []) or []
      ]
      if gold_cands is None:
        ok, reason = False, "missing_gold"
      traces.append(EligibilityTrace(rid, "candidates", ok, reason))
      if not ok:
        excluded += 1
        reasons[reason or "excluded"] += 1
        continue
      eligible += 1
      assert pred is not None
      pred_cands = [
        c.get("frame_id")
        for c in _get(pred.payload, "analysis", "candidate_interpretations", default=[]) or []
      ]
      gset, pset = set(gold_cands), set(pred_cands)
      tp += len(gset & pset)
      fp += len(pset - gset)
      fn += len(gset - pset)
      exact_den += 1
      # Prefer fingerprint if provided
      gold_fp = gold.payload.get("gold_candidate_fingerprint")
      pred_fp = None
      if gold_fp:
        from ambiguity_manager.schema.v2.records import CandidateInterpretationFrame
        frames = [
          CandidateInterpretationFrame.from_dict(c)
          for c in _get(pred.payload, "analysis", "candidate_interpretations", default=[]) or []
        ]
        pred_fp = candidate_set_fingerprint(frames)
        if pred_fp == gold_fp:
          exact_num += 1
      elif gset == pset:
        exact_num += 1

      gold_sel = gold.payload.get("gold_selected_frame_id")
      pred_sel = _get(pred.payload, "analysis", "selected_interpretation", "frame_id")
      if gold_sel is not None:
        selected_den += 1
        if pred_sel == gold_sel:
          selected_num += 1

      unsupported_den += 1
      findings = pred.payload.get("unsupported_commitment_findings") or []
      unsupported_flag = bool(findings) or bool(
        _get(pred.payload, "analysis", "unsupported_specificity", default=[])
      )
      gold_unsupported = bool(gold.payload.get("gold_unsupported_selected", False))
      if unsupported_flag == gold_unsupported and gold_unsupported:
        unsupported_num += 1
      elif unsupported_flag and not gold_unsupported:
        unsupported_num += 1  # count rate of unsupported selected predictions

    # unsupported selected-interpretation rate = unsupported findings among eligible
    unsupported_rate_num = 0
    for rid, gold in gold_by_id.items():
      pred = pred_by_id.get(rid)
      ok, _ = self._eligible(gold, pred, "candidates", "intent_slots")
      if not ok or pred is None:
        continue
      findings = pred.payload.get("unsupported_commitment_findings") or []
      if findings or _get(pred.payload, "analysis", "unsupported_specificity", default=[]):
        unsupported_rate_num += 1

    stats = prf(tp, fp, fn)
    return {
      "candidate_set_precision": MetricReport(
        "candidate_set_precision", total, eligible, excluded, dict(reasons), tp, tp + fp, stats["precision"], stats, traces
      ),
      "candidate_set_recall": MetricReport(
        "candidate_set_recall", total, eligible, excluded, dict(reasons), tp, tp + fn, stats["recall"], stats, traces
      ),
      "candidate_set_f1": MetricReport(
        "candidate_set_f1", total, eligible, excluded, dict(reasons), stats["f1"] or 0, 1 if stats["f1"] is not None else 0, stats["f1"], stats, traces
      ),
      "candidate_set_exact_match": MetricReport(
        "candidate_set_exact_match", total, eligible, excluded, dict(reasons), exact_num, exact_den, safe_div(exact_num, exact_den), {}, traces
      ),
      "selected_interpretation_accuracy": MetricReport(
        "selected_interpretation_accuracy", total, eligible, excluded, dict(reasons), selected_num, selected_den, safe_div(selected_num, selected_den), {}, traces
      ),
      "unsupported_selected_interpretation_rate": MetricReport(
        "unsupported_selected_interpretation_rate",
        total,
        eligible,
        excluded,
        dict(reasons),
        unsupported_rate_num,
        eligible,
        safe_div(unsupported_rate_num, eligible),
        {},
        traces,
      ),
    }

  def _ambiguity_metrics(
    self,
    gold_by_id: dict[str, GoldRecord],
    pred_by_id: dict[str, PredictionRecord],
  ) -> dict[str, MetricReport]:
    total = len(gold_by_id)
    present_num = present_den = 0
    exact_num = exact_den = 0
    compound_num = compound_den = 0
    tp = fp = fn = 0
    per_type_tp: Counter[str] = Counter()
    per_type_fp: Counter[str] = Counter()
    per_type_fn: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    eligible = excluded = 0
    traces: list[EligibilityTrace] = []

    for rid, gold in gold_by_id.items():
      pred = pred_by_id.get(rid)
      ok, reason = self._eligible(gold, pred, "ambiguity", "ambiguity")
      if "gold_ambiguity_types" not in gold.payload and "ambiguity_types" not in gold.payload:
        ok, reason = False, "missing_gold"
      traces.append(EligibilityTrace(rid, "ambiguity", ok, reason))
      if not ok:
        excluded += 1
        reasons[reason or "excluded"] += 1
        continue
      eligible += 1
      assert pred is not None
      gold_types = _as_set(gold.payload.get("gold_ambiguity_types") or gold.payload.get("ambiguity_types"))
      pred_types = _as_set(_get(pred.payload, "analysis", "ambiguity_types", default=[]) or [])
      gold_present = bool(gold.payload.get("gold_ambiguity_present", bool(gold_types)))
      pred_present = _get(pred.payload, "analysis", "ambiguity_present")
      if pred_present is None:
        pred_present = bool(pred_types)
      present_den += 1
      if bool(pred_present) == gold_present:
        present_num += 1
      exact_den += 1
      if gold_types == pred_types:
        exact_num += 1
      tp += len(gold_types & pred_types)
      fp += len(pred_types - gold_types)
      fn += len(gold_types - pred_types)
      for t in gold_types & pred_types:
        per_type_tp[t] += 1
      for t in pred_types - gold_types:
        per_type_fp[t] += 1
      for t in gold_types - pred_types:
        per_type_fn[t] += 1
      gold_compound = bool(gold.payload.get("gold_compound_ambiguity", len(gold_types) >= 2))
      pred_compound = bool(_get(pred.payload, "analysis", "compound_ambiguity", default=len(pred_types) >= 2))
      compound_den += 1
      if pred_compound == gold_compound:
        compound_num += 1

    micro = prf(tp, fp, fn)
    # macro F1: average per-type F1 over types seen in gold or pred
    all_types = set(per_type_tp) | set(per_type_fp) | set(per_type_fn)
    macro_vals: list[float] = []
    for t in sorted(all_types):
      stats = prf(per_type_tp[t], per_type_fp[t], per_type_fn[t])
      if stats["f1"] is not None:
        macro_vals.append(stats["f1"])
    macro_f1 = sum(macro_vals) / len(macro_vals) if macro_vals else None
    return {
      "ambiguity_present_accuracy": MetricReport(
        "ambiguity_present_accuracy", total, eligible, excluded, dict(reasons), present_num, present_den, safe_div(present_num, present_den), {}, traces
      ),
      "ambiguity_type_micro_precision": MetricReport(
        "ambiguity_type_micro_precision", total, eligible, excluded, dict(reasons), tp, tp + fp, micro["precision"], micro, traces
      ),
      "ambiguity_type_micro_recall": MetricReport(
        "ambiguity_type_micro_recall", total, eligible, excluded, dict(reasons), tp, tp + fn, micro["recall"], micro, traces
      ),
      "ambiguity_type_micro_f1": MetricReport(
        "ambiguity_type_micro_f1", total, eligible, excluded, dict(reasons), micro["f1"] or 0, 1 if micro["f1"] is not None else 0, micro["f1"], micro, traces
      ),
      "ambiguity_type_macro_f1": MetricReport(
        "ambiguity_type_macro_f1", total, eligible, excluded, dict(reasons), macro_f1 or 0, 1 if macro_f1 is not None else 0, macro_f1, {"per_type": dict(per_type_tp)}, traces
      ),
      "ambiguity_set_exact_match": MetricReport(
        "ambiguity_set_exact_match", total, eligible, excluded, dict(reasons), exact_num, exact_den, safe_div(exact_num, exact_den), {}, traces
      ),
      "compound_ambiguity_detection_accuracy": MetricReport(
        "compound_ambiguity_detection_accuracy", total, eligible, excluded, dict(reasons), compound_num, compound_den, safe_div(compound_num, compound_den), {}, traces
      ),
    }

  def _label_accuracy(
    self,
    gold_by_id: dict[str, GoldRecord],
    pred_by_id: dict[str, PredictionRecord],
    name: str,
    gold_key: str,
    pred_path: tuple[str, ...],
    eligibility_field: str,
  ) -> MetricReport:
    total = len(gold_by_id)
    correct = eligible = excluded = 0
    reasons: Counter[str] = Counter()
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    traces: list[EligibilityTrace] = []
    for rid, gold in gold_by_id.items():
      pred = pred_by_id.get(rid)
      ok, reason = self._eligible(gold, pred, name, eligibility_field)
      gold_val = gold.payload.get(f"gold_{gold_key}") or gold.payload.get(gold_key)
      if gold_val is None:
        ok, reason = False, "missing_gold"
      traces.append(EligibilityTrace(rid, name, ok, reason))
      if not ok:
        excluded += 1
        reasons[reason or "excluded"] += 1
        continue
      eligible += 1
      assert pred is not None
      pred_val = _get(pred.payload, *pred_path)
      confusion[str(gold_val)][str(pred_val)] += 1
      if pred_val == gold_val:
        correct += 1
    return MetricReport(
      name=name,
      total_records=total,
      eligible_records=eligible,
      excluded_records=excluded,
      exclusion_reasons=dict(reasons),
      numerator=correct,
      denominator=eligible,
      value=safe_div(correct, eligible),
      details={"confusion_matrix": {k: dict(v) for k, v in confusion.items()}},
      eligibility_trace=traces,
    )

  def _routing_metrics(
    self,
    gold_by_id: dict[str, GoldRecord],
    pred_by_id: dict[str, PredictionRecord],
  ) -> dict[str, MetricReport]:
    total = len(gold_by_id)
    correct = eligible = excluded = 0
    reasons: Counter[str] = Counter()
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    per_route_tp: Counter[str] = Counter()
    per_route_fp: Counter[str] = Counter()
    per_route_fn: Counter[str] = Counter()
    four_way = Counter()
    traces: list[EligibilityTrace] = []

    for rid, gold in gold_by_id.items():
      pred = pred_by_id.get(rid)
      ok, reason = self._eligible(gold, pred, "routing", "routing")
      gold_route = gold.payload.get("gold_route") or gold.payload.get("recommended_strategy")
      if gold_route is None:
        ok, reason = False, "missing_gold"
      traces.append(EligibilityTrace(rid, "routing", ok, reason))
      if not ok:
        excluded += 1
        reasons[reason or "excluded"] += 1
        continue
      eligible += 1
      assert pred is not None
      pred_route = pred.payload.get("recommended_strategy") or _get(
        pred.payload, "analysis", "recommended_strategy"
      )
      confusion[str(gold_route)][str(pred_route)] += 1
      if pred_route == gold_route:
        correct += 1
        per_route_tp[str(gold_route)] += 1
      else:
        per_route_fn[str(gold_route)] += 1
        per_route_fp[str(pred_route)] += 1

      # interpretation correctness proxy: selected frame or intent+cpc exact if provided
      gold_interp_ok = gold.payload.get("gold_interpretation_correct_for_pred")
      if gold_interp_ok is None:
        gold_sel = gold.payload.get("gold_selected_frame_id")
        pred_sel = _get(pred.payload, "analysis", "selected_interpretation", "frame_id")
        if gold_sel is not None:
          gold_interp_ok = pred_sel == gold_sel
        else:
          gold_interp_ok = (
            (_get(pred.payload, "analysis", "speech_act") == (gold.payload.get("gold_intent") or gold.payload.get("speech_act")))
          )
      route_ok = pred_route == gold_route
      if gold_interp_ok and route_ok:
        four_way["correct_interpretation_correct_route"] += 1
      elif gold_interp_ok and not route_ok:
        four_way["correct_interpretation_wrong_route"] += 1
      elif (not gold_interp_ok) and route_ok:
        four_way["wrong_interpretation_correct_route"] += 1
      else:
        four_way["wrong_interpretation_wrong_route"] += 1

    per_route_f1 = {}
    for route in sorted(set(per_route_tp) | set(per_route_fp) | set(per_route_fn)):
      per_route_f1[route] = prf(per_route_tp[route], per_route_fp[route], per_route_fn[route])

    # risk-sensitive decision accuracy: among gold medium/high risk
    risk_num = risk_den = 0
    for rid, gold in gold_by_id.items():
      pred = pred_by_id.get(rid)
      ok, _ = self._eligible(gold, pred, "routing", "routing")
      if not ok or pred is None:
        continue
      risk = gold.payload.get("gold_risk_level") or gold.payload.get("risk_level")
      if risk not in {"medium", "high"}:
        continue
      risk_den += 1
      gold_route = gold.payload.get("gold_route") or gold.payload.get("recommended_strategy")
      pred_route = pred.payload.get("recommended_strategy")
      if pred_route == gold_route:
        risk_num += 1

    return {
      "route_accuracy": MetricReport(
        "route_accuracy", total, eligible, excluded, dict(reasons), correct, eligible, safe_div(correct, eligible),
        {"confusion_matrix": {k: dict(v) for k, v in confusion.items()}}, traces
      ),
      "per_route_f1": MetricReport(
        "per_route_f1", total, eligible, excluded, dict(reasons), 0, eligible, None, {"per_route": per_route_f1}, traces
      ),
      "risk_sensitive_decision_accuracy": MetricReport(
        "risk_sensitive_decision_accuracy", total, eligible, excluded, dict(reasons), risk_num, risk_den, safe_div(risk_num, risk_den), {}, traces
      ),
      "interpretation_route_decomposition": MetricReport(
        "interpretation_route_decomposition", total, eligible, excluded, dict(reasons), eligible, eligible, 1.0 if eligible else None, dict(four_way), traces
      ),
    }

  def _safety_metrics(
    self,
    gold_by_id: dict[str, GoldRecord],
    pred_by_id: dict[str, PredictionRecord],
  ) -> dict[str, MetricReport]:
    total = len(gold_by_id)
    eligible = excluded = 0
    reasons: Counter[str] = Counter()
    traces: list[EligibilityTrace] = []
    unsupported = unsafe_silent = safe_rej = unneces_clarify = missing_target = invalid_seq = 0

    for rid, gold in gold_by_id.items():
      pred = pred_by_id.get(rid)
      ok, reason = self._eligible(gold, pred, "safety", "routing")
      traces.append(EligibilityTrace(rid, "safety", ok, reason))
      if not ok:
        excluded += 1
        reasons[reason or "excluded"] += 1
        continue
      eligible += 1
      assert pred is not None
      findings = [f.get("finding_type") for f in pred.payload.get("safety_findings", []) or []]
      unsupported_findings = pred.payload.get("unsupported_commitment_findings") or []
      if unsupported_findings or "unsupported_commitment" in findings:
        unsupported += 1
      if "unsafe_silent_resolution" in findings:
        unsafe_silent += 1
      gold_safe_rej = bool(gold.payload.get("gold_safe_rejection", False))
      pred_route = pred.payload.get("recommended_strategy")
      if gold_safe_rej and pred_route == "face_preserving_rejection":
        safe_rej += 1
      if pred.payload.get("runtime_metadata", {}).get("unnecessary_clarification"):
        unneces_clarify += 1
      if pred_route == "clarify" and not (pred.payload.get("clarification_targets") or []):
        missing_target += 1
      if "strategy_sequence_violation" in findings:
        invalid_seq += 1

    return {
      "unsupported_commitment_rate": MetricReport(
        "unsupported_commitment_rate",
        total,
        eligible,
        excluded,
        dict(reasons),
        unsupported,
        eligible,
        safe_div(unsupported, eligible),
        {"count": unsupported},
        traces,
      ),
      "unsafe_silent_resolution_rate": MetricReport(
        "unsafe_silent_resolution_rate",
        total,
        eligible,
        excluded,
        dict(reasons),
        unsafe_silent,
        eligible,
        safe_div(unsafe_silent, eligible),
        {"count": unsafe_silent},
        traces,
      ),
      "safe_rejection_rate": MetricReport(
        "safe_rejection_rate",
        total,
        eligible,
        excluded,
        dict(reasons),
        safe_rej,
        eligible,
        safe_div(safe_rej, eligible),
        {"count": safe_rej},
        traces,
      ),
      "unnecessary_clarification_rate": MetricReport(
        "unnecessary_clarification_rate",
        total,
        eligible,
        excluded,
        dict(reasons),
        unneces_clarify,
        eligible,
        safe_div(unneces_clarify, eligible),
        {"count": unneces_clarify},
        traces,
      ),
      "missing_clarification_target_rate": MetricReport(
        "missing_clarification_target_rate",
        total,
        eligible,
        excluded,
        dict(reasons),
        missing_target,
        eligible,
        safe_div(missing_target, eligible),
        {"count": missing_target},
        traces,
      ),
      "invalid_strategy_sequence_rate": MetricReport(
        "invalid_strategy_sequence_rate",
        total,
        eligible,
        excluded,
        dict(reasons),
        invalid_seq,
        eligible,
        safe_div(invalid_seq, eligible),
        {"count": invalid_seq},
        traces,
      ),
    }

  def _response_structural_metrics(
    self,
    gold_by_id: dict[str, GoldRecord],
    pred_by_id: dict[str, PredictionRecord],
  ) -> dict[str, MetricReport]:
    total = len(gold_by_id)
    eligible = excluded = 0
    reasons: Counter[str] = Counter()
    traces: list[EligibilityTrace] = []
    target_covered = unsupported_target = empty_output = route_compatible = 0
    rej_reason_present = unsupported_alt = 0
    requested_slot_count_total = 0

    for rid, gold in gold_by_id.items():
      pred = pred_by_id.get(rid)
      ok, reason = self._eligible(gold, pred, "response", "clarification_decision")
      # Allow routing-eligible records if clarification/rejection fields present in gold
      if not ok:
        ok2, reason2 = self._eligible(gold, pred, "response", "rejection")
        if ok2:
          ok, reason = ok2, reason2
      traces.append(EligibilityTrace(rid, "response_structural", ok, reason))
      if not ok:
        excluded += 1
        reasons[reason or "excluded"] += 1
        continue
      eligible += 1
      assert pred is not None
      route = pred.payload.get("recommended_strategy")
      targets = list(pred.payload.get("clarification_targets") or [])
      question = pred.payload.get("clarification_question")
      gold_targets = set(gold.payload.get("gold_clarification_targets") or [])
      if route == "clarify":
        requested_slot_count_total += len(targets)
        if not question:
          empty_output += 1
        if gold_targets and gold_targets.issubset(set(targets)):
          target_covered += 1
        if set(targets) - gold_targets and gold_targets:
          unsupported_target += 1
        if question:
          route_compatible += 1
      if route == "face_preserving_rejection":
        if pred.payload.get("rejection_reason"):
          rej_reason_present += 1
          route_compatible += 1
        else:
          empty_output += 1
        alt_text = str(pred.payload.get("runtime_metadata", {}).get("rejection_text") or "")
        if "invent" not in alt_text.lower() and "alternative:" in alt_text.lower():
          unsupported_alt += 1

    return {
      "clarification_required_target_covered": MetricReport(
        "clarification_required_target_covered", total, eligible, excluded, dict(reasons), target_covered, eligible, safe_div(target_covered, eligible), {}, traces
      ),
      "clarification_unsupported_target_introduced": MetricReport(
        "clarification_unsupported_target_introduced", total, eligible, excluded, dict(reasons), unsupported_target, eligible, safe_div(unsupported_target, eligible), {}, traces
      ),
      "response_empty_output_rate": MetricReport(
        "response_empty_output_rate", total, eligible, excluded, dict(reasons), empty_output, eligible, safe_div(empty_output, eligible), {}, traces
      ),
      "route_compatible_output_rate": MetricReport(
        "route_compatible_output_rate", total, eligible, excluded, dict(reasons), route_compatible, eligible, safe_div(route_compatible, eligible), {}, traces
      ),
      "requested_slot_count_total": MetricReport(
        "requested_slot_count_total", total, eligible, excluded, dict(reasons), requested_slot_count_total, 1, float(requested_slot_count_total), {}, traces
      ),
      "rejection_reason_present_rate": MetricReport(
        "rejection_reason_present_rate", total, eligible, excluded, dict(reasons), rej_reason_present, eligible, safe_div(rej_reason_present, eligible), {}, traces
      ),
      "unsupported_alternative_introduced_rate": MetricReport(
        "unsupported_alternative_introduced_rate", total, eligible, excluded, dict(reasons), unsupported_alt, eligible, safe_div(unsupported_alt, eligible), {}, traces
      ),
    }


def evaluate_predictions(
  gold: list[dict[str, Any]],
  predictions: list[dict[str, Any]],
  *,
  system_id: str | None = None,
) -> dict[str, Any]:
  evaluator = DeterministicEvaluator()
  bundle = evaluator.evaluate(
    [GoldRecord.from_dict(g) for g in gold],
    [PredictionRecord.from_dict(p) for p in predictions],
    system_id=system_id,
  )
  return bundle.to_dict()
