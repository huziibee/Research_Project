"""T24 evaluator hardening tests.

These tests encode the INTENDED, correct behaviour of the deterministic
evaluator. Before the T24 hardening fixes they FAIL against the buggy
evaluator; after the fixes (evaluator.py, eligibility.py,
candidate_generation.py) they PASS.

Synthetic-only. Does not use T13 calibration records. Does not run models.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.evaluation import (  # noqa: E402
    DeterministicEvaluator,
    DuplicatePredictionError,
    evaluate_all_systems,
    evaluate_predictions,
)
from ambiguity_manager.evaluation.eligibility import prf  # noqa: E402
from ambiguity_manager.evaluation.evaluator import (  # noqa: E402
    EvaluationBundle,
    GoldRecord,
    PredictionRecord,
)
from ambiguity_manager.schema.v2.records import CPC, CPCSlot, CandidateInterpretationFrame  # noqa: E402
from ambiguity_manager.schema.v2.taxonomies import (  # noqa: E402
    CPC_SLOT_NAMES,
    CPCSlotStatus,
    METRIC_ELIGIBILITY_FIELDS,
)
from ambiguity_manager.systems.candidate_generation import (  # noqa: E402
    CandidateInterpretationService,
    candidate_set_fingerprint,
    material_cpc_fingerprint,
)


# ---------------------------------------------------------------------------
# Shared fixture builders (synthetic, hand-constructed; not derived from any
# real dataset or from the evaluator itself).
# ---------------------------------------------------------------------------


def _full_eligibility() -> dict[str, bool]:
    return {field: True for field in METRIC_ELIGIBILITY_FIELDS}


def _cpc_dict(**filled: Any) -> dict[str, Any]:
    """Full CPC-shaped dict; unspecified slots are left 'unknown'."""
    data: dict[str, Any] = {
        slot: {"status": "unknown", "value": None} for slot in CPC_SLOT_NAMES
    }
    for slot, value in filled.items():
        data[slot] = {"status": "filled", "value": value}
    return data


def _gold(record_id: str, **overrides: Any) -> GoldRecord:
    payload: dict[str, Any] = {
        "record_id": record_id,
        "gold_intent": "directive_command",
        "gold_cpc": _cpc_dict(),
        "label_eligibility": _full_eligibility(),
    }
    payload.update(overrides)
    return GoldRecord.from_dict(payload)


def _pred(
    record_id: str,
    *,
    system_id: str = "sys",
    intent: str = "directive_command",
    cpc: dict[str, Any] | None = None,
    **overrides: Any,
) -> PredictionRecord:
    analysis: dict[str, Any] = {"speech_act": intent, "cpc": cpc if cpc is not None else _cpc_dict()}
    payload: dict[str, Any] = {
        "record_id": record_id,
        "system_id": system_id,
        "analysis": analysis,
        "execution_status": "ok",
    }
    payload.update(overrides)
    return PredictionRecord.from_dict(payload)


def _frame(frame_id: str, **filled: str) -> CandidateInterpretationFrame:
    cpc = CPC.empty_unknown()
    for slot, value in filled.items():
        setattr(cpc, slot, CPCSlot(value=value, status=CPCSlotStatus.FILLED))
    return CandidateInterpretationFrame(frame_id=frame_id, text=" ".join(filled.values()), cpc=cpc)


class CPCMathematicsTests(unittest.TestCase):
    """CPC slot precision/recall math: TP/FP/FN accounting."""

    def _cpc_metrics(self, gold_cpc: dict, pred_cpc: dict) -> dict[str, Any]:
        gold = _gold("r1", gold_cpc=gold_cpc)
        pred = _pred("r1", cpc=pred_cpc)
        bundle = DeterministicEvaluator().evaluate([gold], [pred])
        assert isinstance(bundle, EvaluationBundle)
        return bundle.to_dict()["metrics"]

    def test_exact_match_is_true_positive(self) -> None:
        metrics = self._cpc_metrics(
            _cpc_dict(action="pick", object="red mug"),
            _cpc_dict(action="pick", object="red mug"),
        )
        self.assertEqual(metrics["cpc_slot_precision"]["numerator"], 2)
        self.assertEqual(metrics["cpc_slot_precision"]["denominator"], 2)
        self.assertEqual(metrics["cpc_slot_precision"]["value"], 1.0)
        self.assertEqual(metrics["cpc_slot_recall"]["value"], 1.0)
        self.assertEqual(metrics["cpc_exact_match"]["value"], 1.0)

    def test_missing_slot_is_false_negative(self) -> None:
        metrics = self._cpc_metrics(
            _cpc_dict(action="pick", object="red mug"),
            _cpc_dict(action="pick"),
        )
        stats = metrics["cpc_slot_precision"]["details"]
        self.assertEqual(stats["tp"], 1)
        self.assertEqual(stats["fp"], 0)
        self.assertEqual(stats["fn"], 1)
        self.assertEqual(metrics["cpc_slot_precision"]["value"], 1.0)
        self.assertEqual(metrics["cpc_slot_recall"]["value"], 0.5)

    def test_extra_slot_is_false_positive(self) -> None:
        metrics = self._cpc_metrics(
            _cpc_dict(action="pick"),
            _cpc_dict(action="pick", object="red mug"),
        )
        stats = metrics["cpc_slot_precision"]["details"]
        self.assertEqual(stats["tp"], 1)
        self.assertEqual(stats["fp"], 1)
        self.assertEqual(stats["fn"], 0)
        self.assertEqual(metrics["cpc_slot_precision"]["value"], 0.5)
        self.assertEqual(metrics["cpc_slot_recall"]["value"], 1.0)

    def test_wrong_value_is_one_fp_and_one_fn(self) -> None:
        """gold action=pick, pred action=move: exactly one FP and one FN."""
        metrics = self._cpc_metrics(
            _cpc_dict(action="pick"),
            _cpc_dict(action="move"),
        )
        stats = metrics["cpc_slot_precision"]["details"]
        self.assertEqual(stats["tp"], 0)
        self.assertEqual(stats["fp"], 1)
        self.assertEqual(stats["fn"], 1)
        self.assertEqual(metrics["cpc_slot_precision"]["value"], 0.0)
        self.assertEqual(metrics["cpc_slot_recall"]["value"], 0.0)
        # Total failure must be reported as 0.0, never hidden as null.
        self.assertEqual(metrics["cpc_slot_f1"]["value"], 0.0)
        self.assertIsNotNone(metrics["cpc_slot_f1"]["value"])

    def test_normalised_equivalent_matches_under_policy(self) -> None:
        """Case/whitespace/trailing-punctuation differences normalise to equal."""
        metrics = self._cpc_metrics(
            _cpc_dict(object="Red   Mug."),
            _cpc_dict(object="red mug"),
        )
        self.assertEqual(metrics["cpc_slot_precision"]["details"]["tp"], 1)
        self.assertEqual(metrics["cpc_slot_precision"]["details"]["fp"], 0)
        self.assertEqual(metrics["cpc_exact_match"]["value"], 1.0)

    def test_list_valued_slot_handled(self) -> None:
        """List-valued slots compare as sets: order must not matter."""
        metrics = self._cpc_metrics(
            _cpc_dict(object=["red mug", "blue bowl"]),
            _cpc_dict(object=["blue bowl", "red mug"]),
        )
        self.assertEqual(metrics["cpc_slot_precision"]["details"]["tp"], 1)
        self.assertEqual(metrics["cpc_slot_precision"]["details"]["fp"], 0)
        self.assertEqual(metrics["cpc_slot_precision"]["details"]["fn"], 0)
        self.assertEqual(metrics["cpc_exact_match"]["value"], 1.0)

        # A genuinely different list must NOT match.
        metrics_diff = self._cpc_metrics(
            _cpc_dict(object=["red mug", "blue bowl"]),
            _cpc_dict(object=["red mug", "green cup"]),
        )
        self.assertEqual(metrics_diff["cpc_exact_match"]["value"], 0.0)

    def test_critical_slot_incorrect_fill_is_not_ignored(self) -> None:
        """A wrong critical-slot value must count against critical_slot_accuracy."""
        metrics = self._cpc_metrics(
            _cpc_dict(action="pick"),
            _cpc_dict(action="place"),
        )
        crit = metrics["critical_slot_accuracy"]
        self.assertEqual(crit["denominator"], 1)
        self.assertEqual(crit["numerator"], 0)
        self.assertEqual(crit["value"], 0.0)

    def test_critical_slot_spurious_fill_enters_denominator(self) -> None:
        """A hallucinated critical-slot fill (gold left it unfilled) must not be
        ignored: it enters the denominator (dragging accuracy down) rather than
        being excluded just because gold has no value there."""
        metrics = self._cpc_metrics(
            _cpc_dict(action="pick"),
            _cpc_dict(action="pick", destination="shelf"),
        )
        crit = metrics["critical_slot_accuracy"]
        # 'action' (gold-filled, matches) and 'destination' (pred-only, critical,
        # spurious) both enter the denominator; only 'action' is correct.
        self.assertEqual(crit["denominator"], 2)
        self.assertEqual(crit["numerator"], 1)
        self.assertEqual(crit["value"], 0.5)


class PRFConventionTests(unittest.TestCase):
    """Precision/recall/F1 null-vs-zero convention (eligibility.prf and evaluator)."""

    def test_support_and_predictions_exist_but_tp_zero_is_zero_not_null(self) -> None:
        stats = prf(tp=0, fp=2, fn=3)
        self.assertEqual(stats["precision"], 0.0)
        self.assertEqual(stats["recall"], 0.0)
        self.assertEqual(stats["f1"], 0.0)
        self.assertIsNotNone(stats["f1"])

    def test_no_gold_positives_and_no_predicted_positives_is_undefined(self) -> None:
        stats = prf(tp=0, fp=0, fn=0)
        self.assertIsNone(stats["precision"])
        self.assertIsNone(stats["recall"])
        self.assertIsNone(stats["f1"])

    def test_no_gold_positives_but_predictions_exist(self) -> None:
        stats = prf(tp=0, fp=3, fn=0)
        self.assertEqual(stats["precision"], 0.0)
        self.assertIsNone(stats["recall"])
        # F1 cannot be computed without a defined recall.
        self.assertIsNone(stats["f1"])

    def test_no_predicted_positives_but_gold_positives_exist(self) -> None:
        stats = prf(tp=0, fp=0, fn=4)
        self.assertIsNone(stats["precision"])
        self.assertEqual(stats["recall"], 0.0)
        self.assertIsNone(stats["f1"])

    def test_never_uses_null_to_hide_total_failure_end_to_end(self) -> None:
        """Two records, complete mismatch on every filled slot: cpc_slot_f1 must
        report 0.0 (total failure), never null."""
        gold_records = [
            _gold("r1", gold_cpc=_cpc_dict(action="pick")),
            _gold("r2", gold_cpc=_cpc_dict(action="open")),
        ]
        preds = [
            _pred("r1", cpc=_cpc_dict(action="move")),
            _pred("r2", cpc=_cpc_dict(action="close")),
        ]
        bundle = DeterministicEvaluator().evaluate(gold_records, preds)
        assert isinstance(bundle, EvaluationBundle)
        f1_report = bundle.to_dict()["metrics"]["cpc_slot_f1"]
        self.assertEqual(f1_report["value"], 0.0)
        self.assertIsNotNone(f1_report["value"])


class CandidateSemanticFingerprintTests(unittest.TestCase):
    """material_cpc_fingerprint / candidate_set_fingerprint semantic identity."""

    def test_identical_content_different_frame_ids_matches(self) -> None:
        a = _frame("f1", action="pick", object="red mug")
        b = _frame("f_other_id", action="pick", object="red mug")
        self.assertEqual(material_cpc_fingerprint(a.cpc), material_cpc_fingerprint(b.cpc))
        self.assertEqual(candidate_set_fingerprint([a]), candidate_set_fingerprint([b]))

    def test_identical_set_different_order_matches(self) -> None:
        a = _frame("f1", action="pick", object="red mug")
        c = _frame("f2", action="bring", object="blue mug")
        self.assertEqual(
            candidate_set_fingerprint([a, c]),
            candidate_set_fingerprint([c, a]),
        )

    def test_one_changed_cpc_slot_fails(self) -> None:
        a = _frame("f1", action="pick", object="red mug")
        changed = _frame("f1", action="pick", object="blue mug")
        self.assertNotEqual(material_cpc_fingerprint(a.cpc), material_cpc_fingerprint(changed.cpc))
        self.assertNotEqual(candidate_set_fingerprint([a]), candidate_set_fingerprint([changed]))

    def test_duplicate_semantic_candidates_detected_deterministically(self) -> None:
        service = CandidateInterpretationService()
        a = _frame("f1", action="bring", object="red mug")
        b = _frame("f2", action="bring", object="red mug")  # same content, different id
        findings_first = service.validate_candidates([a, b])
        findings_second = service.validate_candidates([a, b])
        self.assertTrue(
            any(f.startswith("exact_duplicate_interpretation:") for f in findings_first)
        )
        self.assertEqual(findings_first, findings_second)

    def test_selected_interpretation_comparison_uses_semantic_identity(self) -> None:
        """Selected-interpretation accuracy must match on CPC content, not
        merely on an arbitrary frame_id, when full candidate frames are
        available on both sides."""
        gold_frame = _frame("f_gold_1", action="give", object="cup A")
        gold = _gold(
            "r1",
            gold_selected_frame_id="f_gold_1",
            candidate_interpretations=[gold_frame.to_dict()],
        )
        pred_frame = _frame("f_pred_9", action="give", object="cup A")  # different id, same content
        pred = _pred(
            "r1",
            analysis={
                "speech_act": "directive_command",
                "cpc": _cpc_dict(),
                "candidate_interpretations": [pred_frame.to_dict()],
                "selected_interpretation": {"frame_id": "f_pred_9", "supporting_evidence": []},
            },
        )
        bundle = DeterministicEvaluator().evaluate([gold], [pred])
        assert isinstance(bundle, EvaluationBundle)
        self.assertEqual(
            bundle.to_dict()["metrics"]["selected_interpretation_accuracy"]["value"], 1.0
        )

        # A different id AND different content must not match.
        other_frame = _frame("f_pred_9", action="give", object="cup B")
        pred_wrong = _pred(
            "r1",
            analysis={
                "speech_act": "directive_command",
                "cpc": _cpc_dict(),
                "candidate_interpretations": [other_frame.to_dict()],
                "selected_interpretation": {"frame_id": "f_pred_9", "supporting_evidence": []},
            },
        )
        bundle_wrong = DeterministicEvaluator().evaluate([gold], [pred_wrong])
        assert isinstance(bundle_wrong, EvaluationBundle)
        self.assertEqual(
            bundle_wrong.to_dict()["metrics"]["selected_interpretation_accuracy"]["value"], 0.0
        )


class InterpretationCorrectnessPolicyTests(unittest.TestCase):
    """interpretation_correct = exact intent match AND exact CPC-frame match.

    No intent-only fallback is permitted.
    """

    def _bundle(self, gold: GoldRecord, pred: PredictionRecord) -> dict[str, Any]:
        bundle = DeterministicEvaluator().evaluate([gold], [pred])
        assert isinstance(bundle, EvaluationBundle)
        return bundle.to_dict()["metrics"]

    def test_intent_right_cpc_wrong_is_incorrect(self) -> None:
        gold = _gold("r1", gold_intent="directive_command", gold_cpc=_cpc_dict(action="pick"))
        pred = _pred("r1", intent="directive_command", cpc=_cpc_dict(action="move"))
        metrics = self._bundle(gold, pred)
        self.assertEqual(metrics["interpretation_correctness"]["numerator"], 0)
        self.assertEqual(metrics["interpretation_correctness"]["value"], 0.0)

    def test_intent_wrong_cpc_right_is_incorrect(self) -> None:
        gold = _gold("r1", gold_intent="directive_command", gold_cpc=_cpc_dict(action="pick"))
        pred = _pred("r1", intent="question", cpc=_cpc_dict(action="pick"))
        metrics = self._bundle(gold, pred)
        self.assertEqual(metrics["interpretation_correctness"]["numerator"], 0)
        self.assertEqual(metrics["interpretation_correctness"]["value"], 0.0)

    def test_both_right_is_correct(self) -> None:
        gold = _gold("r1", gold_intent="directive_command", gold_cpc=_cpc_dict(action="pick"))
        pred = _pred("r1", intent="directive_command", cpc=_cpc_dict(action="pick"))
        metrics = self._bundle(gold, pred)
        self.assertEqual(metrics["interpretation_correctness"]["numerator"], 1)
        self.assertEqual(metrics["interpretation_correctness"]["value"], 1.0)

    def test_both_wrong_is_incorrect(self) -> None:
        gold = _gold("r1", gold_intent="directive_command", gold_cpc=_cpc_dict(action="pick"))
        pred = _pred("r1", intent="question", cpc=_cpc_dict(action="move"))
        metrics = self._bundle(gold, pred)
        self.assertEqual(metrics["interpretation_correctness"]["numerator"], 0)
        self.assertEqual(metrics["interpretation_correctness"]["value"], 0.0)

    def test_no_intent_only_fallback(self) -> None:
        """A record with no gold_selected_frame_id: matching intent alone must
        NOT be enough to be judged a correct interpretation if the CPC-frame
        differs. This directly guards against the removed intent-only
        fallback in _routing_metrics / _interpretation_correct."""
        gold = _gold(
            "r1",
            gold_intent="directive_command",
            gold_cpc=_cpc_dict(action="give", object="cup A"),
        )
        pred = _pred(
            "r1",
            intent="directive_command",  # intent matches
            cpc=_cpc_dict(action="give", object="cup B"),  # CPC differs
        )
        self.assertIs(DeterministicEvaluator()._interpretation_correct(gold, pred), False)

    def test_route_decomposition_uses_full_policy_not_intent_only(self) -> None:
        gold = _gold(
            "r1",
            gold_intent="directive_command",
            gold_cpc=_cpc_dict(action="give", object="cup A"),
            gold_route="clarify",
        )
        pred = _pred(
            "r1",
            intent="directive_command",
            cpc=_cpc_dict(action="give", object="cup B"),
            recommended_strategy="clarify",
        )
        bundle = DeterministicEvaluator().evaluate([gold], [pred])
        assert isinstance(bundle, EvaluationBundle)
        decomposition = bundle.to_dict()["metrics"]["interpretation_route_decomposition"]["details"]
        # Route is correct but interpretation is wrong (CPC differs) -> must
        # land in wrong_interpretation_correct_route, not the "correct" bucket.
        self.assertEqual(decomposition.get("wrong_interpretation_correct_route", 0), 1)
        self.assertEqual(decomposition.get("correct_interpretation_correct_route", 0), 0)


class MultiSystemEvaluationTests(unittest.TestCase):
    """Multi-system evaluate()/evaluate_all_systems() semantics."""

    def _seven_system_predictions(self, record_id: str = "r1") -> list[PredictionRecord]:
        return [_pred(record_id, system_id=f"sys_{i}") for i in range(1, 8)]

    def test_seven_system_file_yields_seven_bundles_when_system_absent(self) -> None:
        gold = [_gold("r1")]
        preds = self._seven_system_predictions()
        result = DeterministicEvaluator().evaluate(gold, preds)
        self.assertIsInstance(result, dict)
        self.assertEqual(set(result.keys()), {f"sys_{i}" for i in range(1, 8)})
        for bundle in result.values():
            self.assertIsInstance(bundle, EvaluationBundle)

    def test_evaluate_all_systems_always_returns_dict(self) -> None:
        gold = [_gold("r1")]
        preds = self._seven_system_predictions()
        result = DeterministicEvaluator().evaluate_all_systems(gold, preds)
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result), 7)

        # evaluate_predictions module function mirrors this at the dict level.
        gold_dicts = [{"record_id": "r1", "gold_intent": "directive_command", "gold_cpc": _cpc_dict(), "label_eligibility": _full_eligibility()}]
        pred_dicts = [
            {"record_id": "r1", "system_id": f"sys_{i}", "analysis": {"speech_act": "directive_command"}}
            for i in range(1, 8)
        ]
        all_bundles = evaluate_all_systems(gold_dicts, pred_dicts)
        self.assertEqual(set(all_bundles.keys()), {f"sys_{i}" for i in range(1, 8)})

    def test_explicit_system_yields_one_bundle(self) -> None:
        gold = [_gold("r1")]
        preds = self._seven_system_predictions()
        result = DeterministicEvaluator().evaluate(gold, preds, system_id="sys_3")
        self.assertIsInstance(result, EvaluationBundle)

    def test_duplicate_record_system_pair_raises(self) -> None:
        gold = [_gold("r1")]
        preds = [
            _pred("r1", system_id="sys_1", intent="directive_command"),
            _pred("r1", system_id="sys_1", intent="question"),
        ]
        with self.assertRaises(DuplicatePredictionError):
            DeterministicEvaluator().evaluate(gold, preds, system_id="sys_1")
        with self.assertRaises(DuplicatePredictionError):
            DeterministicEvaluator().evaluate(gold, preds)

    def test_evaluate_predictions_raises_on_duplicate(self) -> None:
        gold_dicts = [{"record_id": "r1", "gold_intent": "directive_command", "gold_cpc": _cpc_dict(), "label_eligibility": _full_eligibility()}]
        pred_dicts = [
            {"record_id": "r1", "system_id": "sys_1", "analysis": {"speech_act": "directive_command"}},
            {"record_id": "r1", "system_id": "sys_1", "analysis": {"speech_act": "question"}},
        ]
        with self.assertRaises(DuplicatePredictionError):
            evaluate_predictions(gold_dicts, pred_dicts, system_id="sys_1")

    def test_mixed_systems_never_overwrite_each_other(self) -> None:
        gold = [_gold("r1", gold_intent="directive_command")]
        preds = [
            _pred("r1", system_id="sys_a", intent="directive_command"),
            _pred("r1", system_id="sys_b", intent="question"),
        ]
        result = DeterministicEvaluator().evaluate(gold, preds)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["sys_a"].metrics["intent_accuracy"].numerator, 1)
        self.assertEqual(result["sys_b"].metrics["intent_accuracy"].numerator, 0)


class ConditionalDenominatorTests(unittest.TestCase):
    """Safety and response-structural metrics use conditional denominators,
    never the full eligible population, and expose the conditional
    numerator/denominator/eligible/excluded/exclusion_reasons breakdown."""

    def test_safe_rejection_rate_denominator_is_gold_eligible_only(self) -> None:
        gold_records = [
            _gold("r_safe", gold_route="face_preserving_rejection", gold_safe_rejection=True),
            _gold("r_execute", gold_route="execute"),
            _gold("r_clarify", gold_route="clarify"),
        ]
        preds = [
            _pred("r_safe", recommended_strategy="face_preserving_rejection", rejection_reason="capability_limitation"),
            _pred("r_execute", recommended_strategy="execute"),
            _pred("r_clarify", recommended_strategy="clarify", clarification_targets=["object"], clarification_question="Which one?"),
        ]
        bundle = DeterministicEvaluator().evaluate(gold_records, preds)
        assert isinstance(bundle, EvaluationBundle)
        safe = bundle.metrics["safe_rejection_rate"]
        self.assertEqual(safe.numerator, 1)
        self.assertEqual(safe.denominator, 1)
        self.assertEqual(safe.value, 1.0)
        self.assertEqual(safe.details["conditional_eligible_count"], 1)
        self.assertEqual(safe.details["conditional_excluded_count"], 2)

        false_rej = bundle.metrics["false_rejection_rate"]
        self.assertEqual(false_rej.numerator, 0)
        self.assertEqual(false_rej.denominator, 2)
        self.assertEqual(false_rej.value, 0.0)

    def test_false_rejection_rate_flags_incorrect_rejections(self) -> None:
        gold_records = [
            _gold("r_execute", gold_route="execute"),
        ]
        preds = [
            _pred("r_execute", recommended_strategy="face_preserving_rejection", rejection_reason="capability_limitation"),
        ]
        bundle = DeterministicEvaluator().evaluate(gold_records, preds)
        assert isinstance(bundle, EvaluationBundle)
        false_rej = bundle.metrics["false_rejection_rate"]
        self.assertEqual(false_rej.numerator, 1)
        self.assertEqual(false_rej.denominator, 1)
        self.assertEqual(false_rej.value, 1.0)

    def test_unnecessary_clarification_rate_denominator_excludes_gold_clarify(self) -> None:
        gold_records = [
            _gold("r_execute", gold_route="execute"),
            _gold("r_clarify_gold", gold_route="clarify"),
        ]
        preds = [
            # Unnecessary: gold did not require clarification but pred clarified.
            _pred("r_execute", recommended_strategy="clarify", clarification_targets=["object"], clarification_question="Which?"),
            # Gold genuinely required clarification: excluded from this
            # conditional denominator regardless of what the system did.
            _pred("r_clarify_gold", recommended_strategy="clarify", clarification_targets=["object"], clarification_question="Which?"),
        ]
        bundle = DeterministicEvaluator().evaluate(gold_records, preds)
        assert isinstance(bundle, EvaluationBundle)
        unneces = bundle.metrics["unnecessary_clarification_rate"]
        self.assertEqual(unneces.numerator, 1)
        self.assertEqual(unneces.denominator, 1)
        self.assertEqual(unneces.value, 1.0)

    def test_clarification_target_coverage_denominator(self) -> None:
        gold_records = [
            _gold("r_covered", gold_route="clarify", gold_clarification_targets=["object"]),
            _gold("r_no_gold_targets", gold_route="clarify", gold_clarification_targets=[]),
            _gold("r_not_clarify", gold_route="execute"),
        ]
        preds = [
            _pred("r_covered", recommended_strategy="clarify", clarification_targets=["object"], clarification_question="Which?"),
            _pred("r_no_gold_targets", recommended_strategy="clarify", clarification_targets=[], clarification_question="Which?"),
            _pred("r_not_clarify", recommended_strategy="execute"),
        ]
        bundle = DeterministicEvaluator().evaluate(gold_records, preds)
        assert isinstance(bundle, EvaluationBundle)
        coverage = bundle.metrics["clarification_required_target_covered"]
        # Only r_covered has both a gold clarify route AND non-empty gold targets.
        self.assertEqual(coverage.denominator, 1)
        self.assertEqual(coverage.numerator, 1)
        self.assertEqual(coverage.value, 1.0)
        self.assertEqual(coverage.details["conditional_eligible_count"], 1)

    def test_rejection_reason_completeness_denominator(self) -> None:
        gold_records = [
            _gold("r_reason", gold_route="face_preserving_rejection"),
            _gold("r_no_reason", gold_route="face_preserving_rejection"),
            _gold("r_executed", gold_route="execute"),
        ]
        preds = [
            _pred("r_reason", recommended_strategy="face_preserving_rejection", rejection_reason="capability_limitation"),
            _pred("r_no_reason", recommended_strategy="face_preserving_rejection", rejection_reason=None),
            _pred("r_executed", recommended_strategy="execute"),
        ]
        bundle = DeterministicEvaluator().evaluate(gold_records, preds)
        assert isinstance(bundle, EvaluationBundle)
        rej_reason = bundle.metrics["rejection_reason_present_rate"]
        # Denominator = predicted-rejection results only (2), not the full
        # eligible population (3).
        self.assertEqual(rej_reason.denominator, 2)
        self.assertEqual(rej_reason.numerator, 1)
        self.assertEqual(rej_reason.value, 0.5)

    def test_every_conditional_metric_exposes_full_breakdown(self) -> None:
        gold_records = [
            _gold("r_safe", gold_route="face_preserving_rejection", gold_safe_rejection=True),
            _gold("r_execute", gold_route="execute"),
        ]
        preds = [
            _pred("r_safe", recommended_strategy="face_preserving_rejection", rejection_reason="capability_limitation"),
            _pred("r_execute", recommended_strategy="execute"),
        ]
        bundle = DeterministicEvaluator().evaluate(gold_records, preds)
        assert isinstance(bundle, EvaluationBundle)
        for name in (
            "safe_rejection_rate",
            "false_rejection_rate",
            "unnecessary_clarification_rate",
        ):
            report = bundle.metrics[name]
            self.assertTrue(hasattr(report, "numerator"))
            self.assertTrue(hasattr(report, "denominator"))
            self.assertTrue(hasattr(report, "eligible_records"))
            self.assertTrue(hasattr(report, "excluded_records"))
            self.assertTrue(hasattr(report, "exclusion_reasons"))
            self.assertIn("conditional_eligible_count", report.details)
            self.assertIn("conditional_excluded_count", report.details)
            self.assertIn("conditional_exclusion_reasons", report.details)


if __name__ == "__main__":
    unittest.main()
