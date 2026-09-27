#!/usr/bin/env python3
"""Score Pilot-120 CPC slot F1 and optional risk-sensitive accuracy.

CPC defaults to the official sidecar when present; otherwise the gold file's
`gold_cpc` (raw T41 merge). Missing/unknown/not_applicable gold cells are
ineligible. Frozen core gold is never mutated.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ambiguity_manager.evaluation.evaluator import (
    DeterministicEvaluator,
    GoldRecord,
    PredictionRecord,
)

ROOT = Path(__file__).resolve().parents[1]
ANN = ROOT / "data" / "annotations" / "pilot_120_v1"
DEFAULT_GOLD = ANN / "pilot_120_final_gold_with_cpc.jsonl"
DEFAULT_CPC_GOLD = ANN / "pilot_120_gold_cpc_official.jsonl"
DEFAULT_RISK_GOLD = ANN / "pilot_120_gold_risk_official.jsonl"
DEFAULT_PRED_CANDIDATES = [
    ROOT
    / "outputs"
    / "cluster_pulls"
    / "r1_manager"
    / "predictions"
    / "goal_first_manager_v2.predictions.jsonl",
    ROOT
    / "pilot120_t41_complete_closure"
    / "frozen_evidence"
    / "R1_manager"
    / "predictions"
    / "full_type_risk_aware_manager.predictions.jsonl",
    ROOT / "outputs" / "gfv2_local_lane_a_rows_20260912.jsonl",
]
OUT_DEFAULT = ROOT / "outputs" / "pilot120_cpc_risk_scores_20260913.json"


def load_jsonl(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows[row["record_id"]] = row
    return rows


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", {}, []):
            return value
    return None


def normalize_prediction(row: dict) -> dict:
    parsed = row.get("parsed") if isinstance(row.get("parsed"), dict) else row
    analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
    if not analysis and any(k in parsed for k in ("cpc", "risk_level", "speech_act")):
        analysis = parsed
    cpc = _first(analysis.get("cpc"), parsed.get("cpc"), row.get("cpc"), {})
    risk = _first(analysis.get("risk_level"), parsed.get("risk_level"), row.get("risk_level"))
    # Prefer the system's scored button (top-level terminal_strategy). The
    # model's analysis recommended_strategy can still say multi_step / silently_resolve
    # after the Python router has already mapped the row.
    route = _first(
        row.get("terminal_strategy"),
        row.get("predicted_terminal_strategy"),
        row.get("predicted_route"),
        parsed.get("terminal_strategy"),
        parsed.get("recommended_strategy"),
        analysis.get("recommended_strategy"),
    )
    speech = _first(analysis.get("speech_act"), parsed.get("speech_act"), row.get("speech_act"))
    return {
        "record_id": row["record_id"],
        "cpc": cpc,
        "analysis": {"cpc": cpc, "speech_act": speech, "risk_level": risk},
        "recommended_strategy": route,
        "risk_level": risk,
    }


def metric_to_dict(report) -> dict:
    return {
        "name": report.name,
        "value": report.value,
        "numerator": report.numerator,
        "denominator": report.denominator,
        "eligible_records": report.eligible_records,
        "excluded_records": report.excluded_records,
        "exclusion_reasons": report.exclusion_reasons,
        "details": report.details,
    }


def prediction_fill_stats(pred_rows: dict[str, dict]) -> dict:
    filled_pred_cells = 0
    filled_pred_rows = 0
    for row in pred_rows.values():
        cpc = row.get("cpc") or {}
        n = 0
        if isinstance(cpc, dict):
            for val in cpc.values():
                if isinstance(val, dict) and val.get("status") == "filled" and val.get("value") not in (None, ""):
                    n += 1
                elif isinstance(val, str) and val:
                    n += 1
        filled_pred_cells += n
        if n:
            filled_pred_rows += 1
    return {
        "rows_with_any_filled_slot": filled_pred_rows,
        "filled_slot_cells": filled_pred_cells,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    ap.add_argument("--pred", type=Path, default=None)
    ap.add_argument("--cpc-gold", type=Path, default=None)
    ap.add_argument("--risk-gold", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args()
    if args.cpc_gold is None and DEFAULT_CPC_GOLD.exists():
        args.cpc_gold = DEFAULT_CPC_GOLD
    if args.risk_gold is None and DEFAULT_RISK_GOLD.exists():
        args.risk_gold = DEFAULT_RISK_GOLD

    if not args.gold.exists():
        raise SystemExit(
            f"Missing merged gold {args.gold}. Run scripts/merge_t41_cpc_into_pilot120_gold.py first."
        )

    pred_path = args.pred
    if pred_path is None:
        for cand in DEFAULT_PRED_CANDIDATES:
            if cand.exists():
                pred_path = cand
                break
    if pred_path is None or not pred_path.exists():
        raise SystemExit("No prediction jsonl found. Pass --pred.")

    gold_rows = load_jsonl(args.gold)
    cpc_overlay_path = None
    if args.cpc_gold and args.cpc_gold.exists():
        cpc_overlay = load_jsonl(args.cpc_gold)
        missing_cpc = sorted(set(gold_rows) - set(cpc_overlay))
        if missing_cpc:
            raise SystemExit(f"CPC gold missing {len(missing_cpc)} ids, e.g. {missing_cpc[:5]}")
        for rid, row in gold_rows.items():
            overlay = cpc_overlay[rid].get("gold_cpc")
            if not isinstance(overlay, dict):
                raise SystemExit(f"CPC gold {rid} has no gold_cpc")
            row["gold_cpc"] = overlay
        cpc_overlay_path = str(args.cpc_gold).replace("\\", "/")
    pred_rows = {rid: normalize_prediction(row) for rid, row in load_jsonl(pred_path).items()}
    missing_pred = sorted(set(gold_rows) - set(pred_rows))
    if missing_pred:
        raise SystemExit(f"Predictions missing {len(missing_pred)} gold ids, e.g. {missing_pred[:5]}")

    gold_by_id = {
        rid: GoldRecord(
            record_id=rid,
            payload={
                **row,
                "gold_route": row.get("terminal_strategy"),
                "label_eligibility": row.get("label_eligibility")
                or {"intent_slots": True, "routing": True, "risk": False},
            },
        )
        for rid, row in gold_rows.items()
    }
    pred_by_id = {
        rid: PredictionRecord(record_id=rid, payload=pred_rows[rid], system_id=pred_path.stem)
        for rid in gold_rows
    }

    harness = DeterministicEvaluator()
    cpc_metrics = harness._cpc_metrics(gold_by_id, pred_by_id)

    risk_block = {
        "status": "blocked_no_official_gold_risk",
        "reason": (
            "pilot_120_final_gold.jsonl never promoted risk_level. "
            "A/B annotations exist (kappa 0.59) but gold-v1 left them exploratory. "
            "Do not score from the system's own risk_level."
        ),
    }
    if args.risk_gold and args.risk_gold.exists():
        risk_rows = load_jsonl(args.risk_gold)
        labeled = sum(1 for r in risk_rows.values() if r.get("gold_risk_level") in {"none", "low", "medium", "high", "unknown"})
        if labeled == 120:
            for rid, row in risk_rows.items():
                gold_by_id[rid].payload["gold_risk_level"] = row.get("gold_risk_level")
                elig = gold_by_id[rid].payload.setdefault("label_eligibility", {})
                elig["risk"] = True
            route_metrics = harness._routing_metrics(gold_by_id, pred_by_id)
            risk_block = {
                "status": "scored_from_supplied_risk_gold",
                "metric": metric_to_dict(route_metrics["risk_sensitive_decision_accuracy"]),
            }
        else:
            risk_block["supplied_labeled_rows"] = labeled

    out = {
        "gold_path": str(args.gold).replace("\\", "/"),
        "cpc_gold_path": cpc_overlay_path,
        "risk_gold_path": str(args.risk_gold).replace("\\", "/") if args.risk_gold else None,
        "pred_path": str(pred_path).replace("\\", "/"),
        "n_gold": len(gold_rows),
        "prediction_cpc_fill": prediction_fill_stats(pred_rows),
        "cpc_slot_f1": metric_to_dict(cpc_metrics["cpc_slot_f1"]),
        "cpc_slot_precision": metric_to_dict(cpc_metrics["cpc_slot_precision"]),
        "cpc_slot_recall": metric_to_dict(cpc_metrics["cpc_slot_recall"]),
        "cpc_exact_match": metric_to_dict(cpc_metrics["cpc_exact_match"]),
        "risk_sensitive_decision_accuracy": risk_block,
        "did_not_invent_gold": True,
        "mutated_frozen_core_gold": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
