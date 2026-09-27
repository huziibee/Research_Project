#!/usr/bin/env python3
"""CPU follow-on: official CPC F1, risk-sensitive accuracy, ask-label, and wording.

Does not mutate frozen core gold.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from score_pilot120_cpc_and_risk import (  # noqa: E402
    DEFAULT_GOLD,
    load_jsonl,
    metric_to_dict,
    normalize_prediction,
    prediction_fill_stats,
)
from ambiguity_manager.evaluation.evaluator import (  # noqa: E402
    DeterministicEvaluator,
    GoldRecord,
    PredictionRecord,
)

ANN = ROOT / "data" / "annotations" / "pilot_120_v1"
OFFICIAL_CPC = ANN / "pilot_120_gold_cpc_official.jsonl"
OFFICIAL_RISK = ANN / "pilot_120_gold_risk_official.jsonl"
OFFICIAL_WORDING = ANN / "pilot_120_gold_wording_official.jsonl"
FROZEN = ANN / "pilot_120_final_gold.jsonl"

DEFAULT_PREDS = [
    ROOT / "outputs" / "cluster_pulls" / "r1_manager" / "predictions" / "goal_first_manager_v2.predictions.jsonl",
    ROOT / "outputs" / "cluster_pulls" / "r1_manager" / "predictions" / "degree_based_router_v2.predictions.jsonl",
    ROOT / "outputs" / "cluster_pulls" / "r1_manager" / "predictions" / "rich_conservative_manager_v2.predictions.jsonl",
    ROOT / "outputs" / "cluster_pulls" / "r1_manager" / "predictions" / "goal_first_context_blind_v2.predictions.jsonl",
    ROOT / "outputs" / "t45_historical_reconciliation_local_20260901" / "inputs" / "direct_base_llm.predictions.jsonl",
    ROOT / "outputs" / "t45_historical_reconciliation_local_20260901" / "inputs" / "t28_selected_adapter_llm.predictions.jsonl",
    ROOT
    / "pilot120_t41_complete_closure"
    / "frozen_evidence"
    / "R1_manager"
    / "predictions"
    / "full_type_risk_aware_manager.predictions.jsonl",
]


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", {}, []):
            return value
    return None


def overlay_official(gold_rows: dict[str, dict], cpc_rows: dict[str, dict], risk_rows: dict[str, dict]) -> dict[str, GoldRecord]:
    out: dict[str, GoldRecord] = {}
    for rid, row in gold_rows.items():
        payload = {
            **row,
            "gold_route": row.get("terminal_strategy"),
            "gold_cpc": cpc_rows[rid]["gold_cpc"],
            "gold_risk_level": risk_rows[rid]["gold_risk_level"],
            "label_eligibility": {"intent_slots": True, "routing": True, "risk": True},
        }
        out[rid] = GoldRecord(record_id=rid, payload=payload)
    return out


def ask_label_prf(gold_rows: dict[str, dict], pred_rows: dict[str, dict]) -> dict[str, Any]:
    tp = fp = fn = 0
    for rid, gold in gold_rows.items():
        gold_ask = gold.get("terminal_strategy") == "clarify"
        pred = pred_rows.get(rid) or {}
        route = _first(pred.get("recommended_strategy"), pred.get("terminal_strategy"))
        pred_ask = route == "clarify"
        if gold_ask and pred_ask:
            tp += 1
        elif pred_ask and not gold_ask:
            fp += 1
        elif gold_ask and not pred_ask:
            fn += 1
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    if rec == 0 and (prec == 0 or prec is None):
        f1 = 0.0
    elif prec is None or rec is None or (prec + rec) == 0:
        f1 = None
    else:
        f1 = 2 * prec * rec / (prec + rec)
    return {
        "status": "official_ask_label_not_wording",
        "gold_ask_rows": 23,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "note": "This is the proposal clarification P/R/F1. It is the ask class, not question wording.",
    }


STOP = {
    "the", "a", "an", "of", "for", "and", "or", "to", "in", "at", "on", "is", "are",
    "with", "from", "that", "this", "already", "chosen", "named", "which",
}


def _tokens(text: str) -> set[str]:
    import re

    # Keep numerals (20 vs 60). Drop other tokens shorter than 3 so "to"/"of" stay out.
    return {
        w
        for w in re.findall(r"[a-z]+|\d+", text.casefold())
        if w not in STOP and (w.isdigit() or len(w) >= 3)
    }


def _item_covered(item: str, blob_tokens: set[str], shared: set[str]) -> bool:
    distinctive = _tokens(item) - shared
    if not distinctive:
        distinctive = _tokens(item)
    if not distinctive:
        return True
    if len(distinctive) == 1:
        return distinctive.issubset(blob_tokens)
    need = 1 if len(distinctive) <= 2 else 2
    return len(distinctive & blob_tokens) >= need


def official_wording_score(raw_pred: dict[str, dict]) -> dict[str, Any]:
    gold = load_jsonl(OFFICIAL_WORDING)
    correct = asked = questions = target_hit = 0
    for rid, row in gold.items():
        pred = raw_pred.get(rid) or {}
        parsed = pred.get("parsed") if isinstance(pred.get("parsed"), dict) else pred
        analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
        route = _first(
            pred.get("terminal_strategy"),
            pred.get("predicted_terminal_strategy"),
            pred.get("predicted_route"),
            parsed.get("terminal_strategy"),
            pred.get("recommended_strategy"),
            parsed.get("recommended_strategy"),
        )
        question = _first(
            pred.get("clarification_question"),
            parsed.get("clarification_question"),
            analysis.get("clarification_question"),
        )
        targets = set(
            _first(
                pred.get("clarification_targets"),
                parsed.get("clarification_targets"),
                analysis.get("clarification_targets"),
                [],
            )
            or []
        )
        gold_targets = set(row["gold_clarification"]["targets"])
        if gold_targets and gold_targets.issubset(targets):
            target_hit += 1
        if route == "clarify":
            asked += 1
        if question:
            questions += 1
            items = row["gold_clarification"]["wording_criteria"]["must_convey"]
            token_sets = [_tokens(x) for x in items]
            shared = set.intersection(*token_sets) if token_sets else set()
            blob = _tokens(str(question))
            if all(_item_covered(item, blob, shared) for item in items):
                correct += 1
    n = len(gold)
    return {
        "status": "official",
        "gold_ask_rows": n,
        "predicted_ask_on_gold_ask": asked,
        "questions_emitted_on_gold_ask": questions,
        "wording_correct": correct,
        "wording_accuracy": correct / n if n else None,
        "target_set_coverage": target_hit / n if n else None,
        "rule": (
            "Denominator is the 23 gold-ask rows. A question is correct if it names "
            "the distinctive licensed alternatives in every must_convey item (paraphrase OK). "
            "No question scores 0."
        ),
    }


def score_one(pred_path: Path, gold_by_id: dict[str, GoldRecord], frozen: dict[str, dict]) -> dict[str, Any]:
    raw = load_jsonl(pred_path)
    pred_rows = {rid: normalize_prediction(row) for rid, row in raw.items()}
    missing = sorted(set(gold_by_id) - set(pred_rows))
    if missing:
        return {"pred_path": str(pred_path).replace("\\", "/"), "status": "missing_predictions", "n_missing": len(missing)}
    pred_by_id = {
        rid: PredictionRecord(record_id=rid, payload=pred_rows[rid], system_id=pred_path.stem)
        for rid in gold_by_id
    }
    harness = DeterministicEvaluator()
    cpc = harness._cpc_metrics(gold_by_id, pred_by_id)
    route = harness._routing_metrics(gold_by_id, pred_by_id)
    return {
        "pred_path": str(pred_path).replace("\\", "/"),
        "system_id": pred_path.stem.replace(".predictions", ""),
        "n": len(gold_by_id),
        "prediction_cpc_fill": prediction_fill_stats(pred_rows),
        "cpc_slot_f1": metric_to_dict(cpc["cpc_slot_f1"]),
        "cpc_slot_precision": metric_to_dict(cpc["cpc_slot_precision"]),
        "cpc_slot_recall": metric_to_dict(cpc["cpc_slot_recall"]),
        "risk_sensitive_decision_accuracy": metric_to_dict(route["risk_sensitive_decision_accuracy"]),
        "clarification_ask_label": ask_label_prf(frozen, pred_rows),
        "clarification_wording": official_wording_score(raw),
    }


def discover(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        found.extend(sorted(root.rglob("*.predictions.jsonl")))
    # Prefer live systems; skip dummy always-* policies.
    skip = {"always_clarify", "always_execute", "always_silently_resolve"}
    out = []
    seen = set()
    for path in found:
        if path.stem.replace(".predictions", "") in skip:
            continue
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "outputs" / "official_sidecar_followon_20260914.json")
    ap.add_argument("--pred", type=Path, action="append", default=[])
    ap.add_argument("--search-root", type=Path, action="append", default=[])
    args = ap.parse_args()

    if not OFFICIAL_CPC.exists() or not OFFICIAL_RISK.exists() or not OFFICIAL_WORDING.exists():
        raise SystemExit("official CPC/risk/wording sidecars missing")

    preds = list(args.pred)
    if args.search_root:
        preds.extend(discover(args.search_root))
    if not preds:
        preds = [p for p in DEFAULT_PREDS if p.exists()]
    if not preds:
        raise SystemExit("no prediction jsonl found")

    frozen = load_jsonl(FROZEN)
    gold_by_id = overlay_official(load_jsonl(DEFAULT_GOLD), load_jsonl(OFFICIAL_CPC), load_jsonl(OFFICIAL_RISK))
    systems = [score_one(path, gold_by_id, frozen) for path in preds]
    payload = {
        "gold_cpc": str(OFFICIAL_CPC).replace("\\", "/"),
        "gold_risk": str(OFFICIAL_RISK).replace("\\", "/"),
        "frozen_core_mutated": False,
        "n_systems_scored": len(systems),
        "gold_wording": str(OFFICIAL_WORDING).replace("\\", "/"),
        "clarification_wording_official": True,
        "qwen_natives": "separate_gpu_job",
        "systems": systems,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "n": len(systems)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
