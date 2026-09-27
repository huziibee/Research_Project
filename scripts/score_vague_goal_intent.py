#!/usr/bin/env python3
"""Deterministic VAGUE goal-triplet scorer; no route/CPC substitution."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from dataset_native_score_diagnostics import modal_joint_baseline, proportion, unique_input_sensitivity

FIELDS = ("subject", "action", "object")


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def norm(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("goal_triplet_value_invalid")
    return re.sub(r"\s+", " ", value).strip().casefold()


def score_rows(gold_rows: list[dict], prediction_rows: list[dict]) -> dict:
    gold = {(row["record_id"], row["condition"]): row for row in gold_rows}
    predictions = {(row["record_id"], row["condition"]): row for row in prediction_rows}
    if len(gold_rows) != 3354 or len(gold) != len(gold_rows):
        raise ValueError("gold_coverage_or_duplicate_mismatch")
    if len(predictions) != len(prediction_rows):
        raise ValueError("prediction_duplicate_evaluation_id")
    if len(predictions) != len(gold) or set(gold) != set(predictions):
        raise ValueError("paired_coverage_mismatch")
    scored = []
    for key, source in gold.items():
        prediction = predictions[key]
        if prediction.get("source_fingerprint_sha256") != source.get("source_fingerprint_sha256"):
            raise ValueError(f"source_fingerprint_mismatch:{key[0]}:{key[1]}")
        target = source["source_target"]["slots"]
        observed = prediction.get("goal_triplet")
        if not isinstance(observed, dict):
            raise ValueError(f"goal_triplet_missing:{key[0]}:{key[1]}")
        if set(observed) != set(FIELDS):
            raise ValueError(f"goal_triplet_schema_invalid:{key[0]}:{key[1]}")
        slot_correct = {field: norm(observed.get(field)) == norm(target.get(field)) for field in FIELDS}
        scored.append({"record_id": key[0], "condition": key[1], "goal_correct": all(slot_correct.values()), **slot_correct})
    by_condition = {}
    for condition in ("command_only", "command_plus_textual_caption"):
        subset = [row for row in scored if row["condition"] == condition]
        by_condition[condition] = proportion(sum(row["goal_correct"] for row in subset), len(subset))
        by_condition[condition]["goal_correct"] = by_condition[condition]["correct"]
    grouped: dict[str, dict[str, bool]] = {}
    for row in scored:
        grouped.setdefault(row["record_id"], {})[row["condition"]] = row["goal_correct"]
    pairs = Counter((values["command_only"], values["command_plus_textual_caption"]) for values in grouped.values())
    n01, n10 = pairs[(False, True)], pairs[(True, False)]
    n = n01 + n10
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(n01, n10) + 1)) / 2**n)
    slot_transitions = {}
    for field in FIELDS:
        values = {}
        for row in scored:
            values.setdefault(row["record_id"], {})[row["condition"]] = row[field]
        slot_transitions[field] = {f"command_only={without}|caption={with_caption}": count for (without,with_caption),count in sorted(Counter((pair["command_only"],pair["command_plus_textual_caption"]) for pair in values.values()).items())}
    # This reports literal slot availability, not semantic evidence quality.
    availability = {"command": Counter(), "caption": Counter()}
    availability_supported = all("command" in source for source in gold_rows)
    seen = set()
    for source in gold_rows:
        if not availability_supported: break
        if source["condition"] != "command_plus_textual_caption" or source["record_id"] in seen: continue
        seen.add(source["record_id"])
        slots = source["source_target"]["slots"]
        for field in FIELDS:
            token = norm(slots[field]); availability["command"][field] += token in norm(source["command"]); availability["caption"][field] += token in norm(source.get("textual_caption") or "")
    availability_result = {"status": "AVAILABLE", **{where: dict(counter) for where, counter in availability.items()}} if availability_supported else {"status": "NOT_AVAILABLE_SOURCE_TEXT_ABSENT"}
    unique_source = [source for source in gold_rows if source["condition"] == "command_plus_textual_caption"]
    modal = modal_joint_baseline(tuple(source["source_target"]["slots"][field] for field in FIELDS) for source in unique_source)
    return {
        "status": "VAGUE_GOAL_INTENT_SCORE_COMPLETE",
        "claim_boundary": "exploratory weak-source-label goal-triplet recovery only",
        "conditions": by_condition,
        "paired_caption_benefit": {"caption_only_correct": n01, "command_only_correct": n10, "difference_caption_minus_command": (n01 - n10) / len(grouped), "exact_mcnemar_p": p},
        "paired_slot_transitions": slot_transitions,
        "literal_target_slot_availability_screen": availability_result,
        "modal_joint_baseline": modal,
        "rows": scored,
    }


def score(gold_path: Path, prediction_path: Path) -> dict:
    return score_rows(rows(gold_path), rows(prediction_path))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--unique-input-ledger", type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError(f"output_exists:{args.out}")
    result = score(args.gold, args.predictions)
    if args.unique_input_ledger:
        ledger = [json.loads(line) for line in args.unique_input_ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
        scored = [{**row, "correct": row["goal_correct"]} for row in result["rows"]]
        result["unique_input_sensitivity"] = {
            condition: unique_input_sensitivity(scored, ledger, correct_field="correct", condition=condition)
            for condition in ("command_only", "command_plus_textual_caption")
        }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "rows": len(result["rows"])}, sort_keys=True))


if __name__ == "__main__":
    main()
