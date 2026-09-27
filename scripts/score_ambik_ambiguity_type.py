#!/usr/bin/env python3
"""Exact-set AmbiK ambiguity-type scorer; no clarification semantic proxy."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from dataset_native_score_diagnostics import modal_joint_baseline, proportion, unique_input_sensitivity

ALLOWED = {"commonsense", "preference", "safety_precondition"}


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def types(value: object) -> list[str]:
    if not isinstance(value, list) or len(set(value)) != len(value):
        raise ValueError("ambiguity_types_invalid")
    if not value:
        return []
    if set(value) - ALLOWED:
        raise ValueError("ambiguity_types_invalid")
    return sorted(value)


def score_rows(key_rows: list[dict], prediction_rows: list[dict], ledger_rows: list[dict] | None = None) -> dict:
    key = {row["record_id"]: row for row in key_rows}
    predictions = {row["record_id"]: row for row in prediction_rows}
    if len(key) != 1000 or len(key) != len(key_rows) or len(predictions) != len(prediction_rows) or set(key) != set(predictions):
        raise ValueError("coverage_or_duplicate_mismatch")
    scored = []
    for record_id, gold in key.items():
        prediction = predictions[record_id]
        if prediction.get("source_fingerprint_sha256") != gold.get("source_fingerprint_sha256"):
            raise ValueError(f"source_fingerprint_mismatch:{record_id}")
        scored.append({
            "record_id": record_id,
            "gold": types(gold["ambiguity_types"]),
            "predicted": types(prediction.get("ambiguity_types")),
            "correct": types(gold["ambiguity_types"]) == types(prediction.get("ambiguity_types")),
        })
    gold_type = lambda row: row["gold"][0] if len(row["gold"]) == 1 else json.dumps(row["gold"])
    predicted_type = lambda row: row["predicted"][0] if len(row["predicted"]) == 1 else json.dumps(row["predicted"])
    per_type = {}
    for label in sorted(ALLOWED):
        subset = [row for row in scored if gold_type(row) == label]
        predicted_as = [row for row in scored if predicted_type(row) == label]
        true_positive = sum(row["correct"] for row in subset)
        per_type[label] = {
            **proportion(true_positive, len(subset)),
            "exact_set_recall": true_positive / len(subset) if subset else None,
            "precision": true_positive / len(predicted_as) if predicted_as else None,
        }
    confusion = Counter((gold_type(row), predicted_type(row)) for row in scored)
    observed_recalls = [row["exact_set_recall"] for row in per_type.values() if row["exact_set_recall"] is not None]
    result = {
        "status": "AMBIK_AMBIGUITY_TYPE_SCORE_COMPLETE",
        "claim_boundary": "exploratory source-mapped ambiguity-type recovery only",
        "n": len(scored),
        "correct": sum(row["correct"] for row in scored),
        "accuracy": sum(row["correct"] for row in scored) / len(scored),
        "accuracy_interval": proportion(sum(row["correct"] for row in scored), len(scored)),
        "per_gold_type_exact_set_recall": per_type,
        "macro_exact_set_recall": sum(observed_recalls) / len(observed_recalls),
        "confusion_matrix": {f"gold={gold}|predicted={predicted}": count for (gold, predicted), count in sorted(confusion.items())},
        "modal_joint_baseline": modal_joint_baseline(row["gold"] for row in scored),
        "rows": scored,
    }
    if ledger_rows is not None:
        result["unique_input_sensitivity"] = unique_input_sensitivity(scored, ledger_rows)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--unique-input-ledger", type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError(f"output_exists:{args.out}")
    ledger = load(args.unique_input_ledger) if args.unique_input_ledger else None
    args.out.write_text(json.dumps(score_rows(load(args.key), load(args.predictions), ledger), indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
