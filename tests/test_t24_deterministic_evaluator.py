from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.evaluation.evaluator import (  # noqa: E402
    DeterministicEvaluator,
    GoldRecord,
    PredictionRecord,
    evaluate_predictions,
)

FIXTURES_DIR = ROOT / "tests" / "fixtures" / "t16_t24_synthetic"
GOLD_PATH = FIXTURES_DIR / "gold.jsonl"
EXPECTED_PATH = FIXTURES_DIR / "expected_metrics.json"
CACHED_ANALYSES_PATH = FIXTURES_DIR / "cached_analyses.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _merge_dicts(base: dict, overrides: dict) -> dict:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_dicts(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


class DeterministicEvaluatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gold_rows = _load_jsonl(GOLD_PATH)
        cls.gold_by_id = {row["record_id"]: row for row in cls.gold_rows}
        cls.expected = _load_json(EXPECTED_PATH)
        cls.cached_analyses = _load_json(CACHED_ANALYSES_PATH)

    def build_prediction(
        self,
        record_id: str,
        *,
        system_id: str = "test_system",
        overrides: dict | None = None,
    ) -> dict:
        gold = self.gold_by_id[record_id]
        analysis = copy.deepcopy(self.cached_analyses[record_id])
        route = gold.get("gold_route")
        clarification_targets = list(gold.get("gold_clarification_targets") or [])
        prediction = {
            "record_id": record_id,
            "system_id": system_id,
            "system_version": "test-1.0.0",
            "analysis": analysis,
            "recommended_strategy": route,
            "strategy_sequence": [route] if route == "multi_step" else [],
            "clarification_targets": clarification_targets if route == "clarify" else [],
            "clarification_question": (
                "Which object do you mean?" if route == "clarify" else None
            ),
            "resolved_slots": list(analysis.get("resolved_slots") or []),
            "rejection_reason": (
                "capability_limitation"
                if route == "face_preserving_rejection"
                else None
            ),
            "unsupported_commitment_findings": [],
            "safety_findings": [],
            "execution_status": "ok",
            "provider_provenance": {},
            "runtime_metadata": {},
            "synthetic_only": True,
            "official_result": False,
        }
        if overrides:
            prediction = _merge_dicts(prediction, copy.deepcopy(overrides))
        return prediction

    def evaluate_subset(
        self,
        record_ids: list[str],
        predictions: list[dict],
        *,
        system_id: str = "test_system",
    ) -> dict:
        gold = [self.gold_by_id[record_id] for record_id in record_ids]
        return evaluate_predictions(gold, predictions, system_id=system_id)

    def test_core4_hand_calculated_fixture_matches_expected_metrics_json(self) -> None:
        record_ids = list(self.expected["records"])
        predictions = [
            self.build_prediction(record_id, system_id="core4")
            for record_id in record_ids
        ]
        bundle = self.evaluate_subset(record_ids, predictions, system_id="core4")
        metrics = bundle["metrics"]

        intent_expected = self.expected["intent_accuracy"]
        intent_report = metrics["intent_accuracy"]
        for field in (
            "total_records",
            "eligible_records",
            "excluded_records",
            "numerator",
            "denominator",
            "value",
        ):
            self.assertEqual(intent_report[field], intent_expected[field])
        self.assertEqual(intent_report["exclusion_reasons"], intent_expected["exclusion_reasons"])
        self.assertEqual(
            intent_report["details"]["confusion_matrix"],
            {"directive_command": {"directive_command": 3}},
        )

        route_expected = self.expected["route_accuracy"]
        route_report = metrics["route_accuracy"]
        for field in (
            "total_records",
            "eligible_records",
            "excluded_records",
            "numerator",
            "denominator",
            "value",
        ):
            self.assertEqual(route_report[field], route_expected[field])

        ambiguity_expected = self.expected["ambiguity_micro"]
        self.assertEqual(
            metrics["ambiguity_type_micro_precision"]["value"],
            ambiguity_expected["precision"],
        )
        self.assertEqual(
            metrics["ambiguity_type_micro_recall"]["value"],
            ambiguity_expected["recall"],
        )
        self.assertEqual(
            metrics["ambiguity_type_micro_f1"]["value"],
            ambiguity_expected["f1"],
        )

        clear_only = self.evaluate_subset(
            ["syn_clear_execute"],
            [self.build_prediction("syn_clear_execute", system_id="core4")],
            system_id="core4",
        )["metrics"]
        cpc_expected = self.expected["cpc_slot_prf"]
        self.assertEqual(clear_only["cpc_slot_precision"]["numerator"], cpc_expected["tp"])
        self.assertEqual(
            clear_only["cpc_slot_precision"]["denominator"],
            cpc_expected["tp"] + cpc_expected["fp"],
        )
        self.assertEqual(clear_only["cpc_slot_precision"]["value"], cpc_expected["precision"])
        self.assertEqual(clear_only["cpc_slot_recall"]["value"], cpc_expected["recall"])
        self.assertEqual(clear_only["cpc_slot_f1"]["value"], cpc_expected["f1"])
        self.assertEqual(clear_only["cpc_exact_match"]["value"], 1.0)
        self.assertEqual(clear_only["critical_slot_accuracy"]["numerator"], 2)
        self.assertEqual(clear_only["critical_slot_accuracy"]["denominator"], 2)
        self.assertEqual(clear_only["joint_intent_cpc"]["value"], 1.0)

    def test_candidate_metrics_cover_precision_recall_f1_and_exact_match(self) -> None:
        record_id = "syn_correct_route_wrong_interp"
        gold = [self.gold_by_id[record_id]]
        first_candidate = copy.deepcopy(
            self.cached_analyses[record_id]["candidate_interpretations"][0]
        )
        extra_candidate = copy.deepcopy(first_candidate)
        extra_candidate["frame_id"] = "f_extra"
        prediction = self.build_prediction(
            record_id,
            overrides={
                "analysis": {
                    "candidate_interpretations": [first_candidate, extra_candidate],
                    "selected_interpretation": {"frame_id": "f_a", "supporting_evidence": []},
                }
            },
        )

        metrics = evaluate_predictions(gold, [prediction])["metrics"]
        self.assertEqual(metrics["candidate_set_precision"]["value"], 0.5)
        self.assertEqual(metrics["candidate_set_recall"]["value"], 0.5)
        self.assertEqual(metrics["candidate_set_f1"]["value"], 0.5)
        self.assertEqual(metrics["candidate_set_exact_match"]["value"], 0.0)
        self.assertEqual(metrics["selected_interpretation_accuracy"]["value"], 0.0)

    def test_ambiguity_metrics_cover_micro_macro_and_exact_set_match(self) -> None:
        record_ids = ["syn_referential_clarify", "syn_compound_multistep"]
        predictions = [self.build_prediction(record_id) for record_id in record_ids]

        metrics = self.evaluate_subset(record_ids, predictions)["metrics"]
        self.assertEqual(metrics["ambiguity_type_micro_precision"]["value"], 1.0)
        self.assertEqual(metrics["ambiguity_type_micro_recall"]["value"], 1.0)
        self.assertEqual(metrics["ambiguity_type_micro_f1"]["value"], 1.0)
        self.assertEqual(metrics["ambiguity_type_macro_f1"]["value"], 1.0)
        self.assertEqual(metrics["ambiguity_set_exact_match"]["value"], 1.0)
        self.assertEqual(metrics["compound_ambiguity_detection_accuracy"]["value"], 1.0)

    def test_risk_and_capability_accuracy_report_confusion(self) -> None:
        record_ids = ["syn_clear_execute", "syn_unknown_risk_clarify"]
        predictions = [
            self.build_prediction("syn_clear_execute"),
            self.build_prediction(
                "syn_unknown_risk_clarify",
                overrides={
                    "analysis": {
                        "risk_level": "low",
                        "capability_status": "capable",
                    }
                },
            ),
        ]

        metrics = self.evaluate_subset(record_ids, predictions)["metrics"]
        self.assertEqual(metrics["risk_accuracy"]["value"], 0.5)
        self.assertEqual(metrics["capability_accuracy"]["value"], 0.5)
        self.assertEqual(
            metrics["risk_accuracy"]["details"]["confusion_matrix"]["unknown"]["low"],
            1,
        )
        self.assertEqual(
            metrics["capability_accuracy"]["details"]["confusion_matrix"]["conditional"][
                "capable"
            ],
            1,
        )

    def test_route_metrics_include_per_route_f1_and_four_way_decomposition(self) -> None:
        record_ids = [
            "syn_clear_execute",
            "syn_wrong_route_correct_interp",
            "syn_correct_route_wrong_interp",
            "syn_incapable_reject",
        ]
        predictions = [
            self.build_prediction("syn_clear_execute"),
            self.build_prediction(
                "syn_wrong_route_correct_interp",
                overrides={"recommended_strategy": "clarify"},
            ),
            self.build_prediction("syn_correct_route_wrong_interp"),
            self.build_prediction(
                "syn_incapable_reject",
                overrides={
                    "recommended_strategy": "execute",
                    "analysis": {
                        "selected_interpretation": {
                            "frame_id": "wrong-frame",
                            "supporting_evidence": [],
                        }
                    },
                },
            ),
        ]

        metrics = self.evaluate_subset(record_ids, predictions)["metrics"]
        self.assertEqual(metrics["route_accuracy"]["numerator"], 2)
        self.assertEqual(metrics["route_accuracy"]["denominator"], 4)
        self.assertEqual(metrics["route_accuracy"]["value"], 0.5)

        decomposition = metrics["interpretation_route_decomposition"]["details"]
        self.assertEqual(decomposition["correct_interpretation_correct_route"], 1)
        self.assertEqual(decomposition["correct_interpretation_wrong_route"], 1)
        self.assertEqual(decomposition["wrong_interpretation_correct_route"], 1)
        self.assertEqual(decomposition["wrong_interpretation_wrong_route"], 1)

        per_route = metrics["per_route_f1"]["details"]["per_route"]
        self.assertIn("execute", per_route)
        self.assertIn("clarify", per_route)
        self.assertIn("face_preserving_rejection", per_route)

    def test_safety_rates_cover_requested_behavioral_counts(self) -> None:
        record_ids = [
            "syn_clear_execute",
            "syn_unsupported_silent",
            "syn_prohibited_reject",
            "syn_unnecessary_clarify",
        ]
        predictions = [
            self.build_prediction("syn_clear_execute"),
            self.build_prediction(
                "syn_unsupported_silent",
                overrides={
                    "recommended_strategy": "silently_resolve",
                    "unsupported_commitment_findings": [
                        {"finding_type": "unsupported_commitment"}
                    ],
                    "safety_findings": [
                        {"finding_type": "unsafe_silent_resolution"}
                    ],
                },
            ),
            self.build_prediction("syn_prohibited_reject"),
            self.build_prediction(
                "syn_unnecessary_clarify",
                overrides={
                    "recommended_strategy": "clarify",
                    "runtime_metadata": {"unnecessary_clarification": True},
                },
            ),
        ]

        metrics = self.evaluate_subset(record_ids, predictions)["metrics"]
        self.assertEqual(metrics["unsupported_commitment_rate"]["value"], 0.25)
        self.assertEqual(metrics["unsafe_silent_resolution_rate"]["value"], 0.25)
        self.assertEqual(metrics["safe_rejection_rate"]["value"], 0.25)
        self.assertEqual(metrics["unnecessary_clarification_rate"]["value"], 0.25)

    def test_missing_gold_and_missing_prediction_change_denominators_per_metric(self) -> None:
        record_ids = [
            "syn_clear_execute",
            "syn_referential_clarify",
            "syn_missing_gold_intent",
        ]
        gold_records = [GoldRecord.from_dict(self.gold_by_id[record_id]) for record_id in record_ids]
        predictions = [
            PredictionRecord.from_dict(self.build_prediction("syn_clear_execute"))
        ]

        bundle = DeterministicEvaluator().evaluate(gold_records, predictions)
        intent = bundle.metrics["intent_accuracy"]
        self.assertEqual(intent.eligible_records, 1)
        self.assertEqual(intent.excluded_records, 2)
        self.assertEqual(intent.exclusion_reasons["missing_prediction"], 1)
        self.assertEqual(intent.exclusion_reasons["missing_gold"], 1)
        self.assertEqual(intent.denominator, 1)

        route = bundle.metrics["route_accuracy"]
        self.assertEqual(route.eligible_records, 1)
        self.assertEqual(route.excluded_records, 2)
        self.assertEqual(route.exclusion_reasons, {"missing_prediction": 2})
        self.assertEqual(route.denominator, 1)


if __name__ == "__main__":
    unittest.main()
