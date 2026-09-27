#!/usr/bin/env python3
"""Deterministic weak-source-label scorers for CLARA and Indirect Requests."""
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


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def norm(xs):
    return sorted(" ".join(x.casefold().split()) for x in xs)


def score_rows(task: str, key_rows: list[dict], prediction_rows: list[dict], ledger_rows: list[dict] | None = None) -> dict:
    key = {row["record_id"]: row for row in key_rows}
    expected = len(key) * (2 if task == "clara" else 1)
    if len(prediction_rows) != expected or len({(row["record_id"], row["condition"]) for row in prediction_rows}) != expected:
        raise ValueError("coverage_mismatch")
    fields = ("ambiguity_present", "capability_status", "recommended_strategy") if task == "clara" else ("ambiguity_present", "ambiguity_types", "missing_slots")
    rows = []
    for prediction in prediction_rows:
        gold = key[prediction["record_id"]]
        if prediction["source_fingerprint_sha256"] != gold["source_fingerprint_sha256"]:
            raise ValueError("fingerprint_mismatch")
        checks = {field: (norm(prediction[field]) == norm(gold[field]) if isinstance(gold[field], list) else prediction[field] == gold[field]) for field in fields}
        rows.append({
            "record_id": prediction["record_id"],
            "condition": prediction["condition"],
            "correct": all(checks.values()),
            "predicted_ambiguity_present": prediction.get("ambiguity_present"),
            **checks,
        })
    field_scores = {field: proportion(sum(row[field] for row in rows), len(rows)) for field in fields}
    if task == "clara":
        gold_labels = [(gold["ambiguity_present"], gold["capability_status"], gold["recommended_strategy"]) for gold in key.values()]
    else:
        gold_labels = [(gold["ambiguity_present"], gold["ambiguity_types"], gold["missing_slots"]) for gold in key.values()]
    result = {
        "status": "NATIVE_CONTEXT_SCORE_COMPLETE",
        "task": task,
        "claim_boundary": "exploratory weak-source-label only",
        "n": len(rows),
        "correct": sum(row["correct"] for row in rows),
        "accuracy": sum(row["correct"] for row in rows) / len(rows),
        "accuracy_interval": proportion(sum(row["correct"] for row in rows), len(rows)),
        "field_scores": field_scores,
        "modal_joint_baseline": modal_joint_baseline(gold_labels),
        "rows": rows,
    }
    if task == "clara":
        by_id = {}
        for row in rows:
            by_id.setdefault(row["record_id"], {})[row["condition"]] = row
        if any(set(pair) != {"full_context", "context_blind"} for pair in by_id.values()):
            raise ValueError("clara_pair_coverage_mismatch")
        result["paired_joint_transitions"] = {
            f"context_blind={blind}|full_context={full}": count
            for (blind, full), count in sorted(Counter((pair["context_blind"]["correct"], pair["full_context"]["correct"]) for pair in by_id.values()).items())
        }
        result["paired_field_transitions"] = {
            field: {
                f"context_blind={blind}|full_context={full}": count
                for (blind, full), count in sorted(Counter((pair["context_blind"][field], pair["full_context"][field]) for pair in by_id.values()).items())
            }
            for field in fields
        }
        if ledger_rows is not None:
            result["unique_input_sensitivity"] = {
                "full_context": unique_input_sensitivity(rows, ledger_rows, condition="full_context"),
                "context_blind": unique_input_sensitivity(rows, ledger_rows, condition="context_blind"),
            }
    else:
        ambiguity = [(key[row["record_id"]]["ambiguity_present"], row["predicted_ambiguity_present"]) for row in rows]
        matrix = Counter(ambiguity)
        tp, fn, fp, tn = matrix[(True, True)], matrix[(True, False)], matrix[(False, True)], matrix[(False, False)]
        result["ambiguity_present_confusion"] = {
            "true_positive": tp,
            "false_negative": fn,
            "false_positive": fp,
            "true_negative": tn,
            "positive_recall": tp / (tp + fn) if tp + fn else None,
            "positive_precision": tp / (tp + fp) if tp + fp else None,
            "balanced_accuracy": ((tp / (tp + fn)) + (tn / (tn + fp))) / 2 if (tp + fn and tn + fp) else None,
        }
        if ledger_rows is not None:
            result["unique_input_sensitivity"] = unique_input_sensitivity(rows, ledger_rows)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=("clara", "indirect"), required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--unique-input-ledger", type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError("output_exists")
    ledger = load(args.unique_input_ledger) if args.unique_input_ledger else None
    result = score_rows(args.task, load(args.key), load(args.predictions), ledger)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
