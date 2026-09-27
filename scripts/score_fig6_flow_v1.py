#!/usr/bin/env python3
"""Exploratory Fig. 6 text-flow scorer; never treats proposed gates as gold.

Input JSONL has one row per frozen Pilot-120 case:
  {"record_id": "CA-0007", "route": "clarify",
   "first_blocking_gate": "grounded",
   "gates": {"grounded": null, "one_atomic_action": true, "capable": true,
             "authorized": null, "risk_acceptable": null},
   "cpc": {"action": {"status": "filled", "value": "deliver"}, ...}}

All 13 CPC slots and the first blocking gate are required on successful rows.
A slot can be filled, missing, unknown, or not_applicable. Gate values are
true, false, or null. Null means unverified.
This scorer reports gate distributions only: no independent gate labels exist.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ambiguity_manager.systems.fig6_flow_v1 import Fig6GateInput, route_fig6  # noqa: E402
ANN = ROOT / "data" / "annotations" / "pilot_120_v1"
INPUTS = {
    "source_canonical.jsonl": "f33b1e29f1e8aa256a475f07213aa07247def47d8e2148d54a472a40b71b05c9",
    "pilot_120_final_gold.jsonl": "5e23ad1a92ff1873c8f039a8ce560a111dd6fb6b8ae8c11d6cf34dbfa1c360db",
    "pilot_120_gold_cpc_official.jsonl": "ab990cbaf32967390adf59cf860a159c5461c1c0f6dba07d0eb2ce989a7beee7",
    "pilot_120_gold_risk_official.jsonl": "9273fd41aeb4fd336e441977c73b6b17d7b1e6e4f87da86ad974aea878fe1ac7",
}
SLOTS = (
    "action", "actor", "conditions", "constraints", "destination", "negation",
    "object", "object_attributes", "quantity", "recipient", "spatial_relation",
    "time", "tool",
)
AMBIGUITY_TYPES = (
    "pragmatic", "discourse_ellipsis", "lexical", "scope", "object_reference",
    "pronoun_reference", "recipient_reference", "destination_reference",
    "instrument_reference", "spatial_reference", "temporal_reference",
    "routine_reference", "action_order", "fuzzy_temporal", "fuzzy_quantity",
    "degree_vagueness", "endpoint_vagueness",
)
GATES = ("grounded", "one_atomic_action", "capable", "authorized", "risk_acceptable")
ROUTES = ("execute", "clarify", "face_preserving_rejection")
SLOT_STATUSES = {"filled", "missing", "unknown", "not_applicable"}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_rows(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or not isinstance(row.get("record_id"), str):
                raise ValueError(f"{path}:{number}: object with record_id required")
            rid = row["record_id"]
            if rid in rows:
                raise ValueError(f"{path}:{number}: duplicate record_id {rid}")
            rows[rid] = row
    return rows


def normalized(value: Any) -> str:
    """Versioned CPC v1 scalar normalization; never fuzzy-match text."""
    if isinstance(value, list):
        return "|".join(sorted(normalized(item) for item in value))
    if not isinstance(value, str):
        raise ValueError(f"CPC filled value must be text or text list: {value!r}")
    return " ".join(value.lower().strip().rstrip(".,;:!?").split())


def pred_slot_value(slot: Any, rid: str, name: str) -> str | None:
    if not isinstance(slot, dict) or set(slot) != {"status", "value"}:
        raise ValueError(f"{rid} cpc.{name}: expected status/value object")
    status, value = slot["status"], slot["value"]
    if status not in SLOT_STATUSES:
        raise ValueError(f"{rid} cpc.{name}: invalid status {status!r}")
    if status == "filled":
        result = normalized(value)
        if not result:
            raise ValueError(f"{rid} cpc.{name}: empty filled value")
        return result
    if value is not None:
        raise ValueError(f"{rid} cpc.{name}: unfilled value must be null")
    return None


def fraction(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def score(pred_path: Path) -> dict[str, Any]:
    for name, expected in INPUTS.items():
        observed = digest(ANN / name)
        if observed != expected:
            raise ValueError(f"frozen input hash mismatch: {name}: {observed}")
    source = load_rows(ANN / "source_canonical.jsonl")
    gold = load_rows(ANN / "pilot_120_final_gold.jsonl")
    cpc_gold = load_rows(ANN / "pilot_120_gold_cpc_official.jsonl")
    risk_gold = load_rows(ANN / "pilot_120_gold_risk_official.jsonl")
    preds = load_rows(pred_path)
    ids = set(gold)
    if len(ids) != 120 or any(set(rows) != ids for rows in (source, cpc_gold, risk_gold, preds)):
        raise ValueError("source, gold, sidecars, and predictions require the same 120 unique IDs")

    confusion: dict[str, Counter[str]] = {route: Counter() for route in ROUTES}
    gates: dict[str, Counter[str]] = {name: Counter() for name in GATES}
    first_blocking_gate: Counter[str] = Counter()
    risk_counts: Counter[str] = Counter()
    slot_eligible: Counter[str] = Counter()
    slot_correct: Counter[str] = Counter()
    unsupported: Counter[str] = Counter()
    ambiguity_tp: Counter[str] = Counter()
    ambiguity_fp: Counter[str] = Counter()
    ambiguity_fn: Counter[str] = Counter()
    ambiguity_exact = 0
    unresolved_slot_counts: Counter[str] = Counter()
    alternative_count = 0
    material_filled = material_quote_supported = 0
    route_correct = cpc_exact = joint_exact = false_execute = false_refusal = failed = 0
    unsupported_records = 0
    for rid in sorted(ids):
        pred, g, cg = preds[rid], gold[rid], cpc_gold[rid]
        route, gold_route = pred.get("route"), g.get("terminal_strategy")
        if gold_route not in ROUTES:
            raise ValueError(f"{rid}: invalid gold route")
        is_failed = route is None
        if not is_failed and route not in ROUTES:
            raise ValueError(f"{rid}: invalid prediction route {route!r}")
        if is_failed:
            failed += 1
            first_blocking_gate["failed"] += 1
            for name in GATES:
                gates[name]["unknown"] += 1
        else:
            if "first_blocking_gate" not in pred or (
                pred["first_blocking_gate"] is not None
                and pred["first_blocking_gate"] not in GATES
            ):
                raise ValueError(f"{rid}: invalid first_blocking_gate")
            first_blocking_gate[
                "no_blocker" if pred["first_blocking_gate"] is None
                else pred["first_blocking_gate"]
            ] += 1
            if not isinstance(pred.get("gates"), dict) or set(pred["gates"]) != set(GATES):
                raise ValueError(f"{rid}: five Fig. 6 gates required")
            if not isinstance(pred.get("cpc"), dict) or set(pred["cpc"]) != set(SLOTS):
                raise ValueError(f"{rid}: all 13 CPC slots required")
            for name in GATES:
                value = pred["gates"][name]
                if value is not None and type(value) is not bool:
                    raise ValueError(f"{rid} gates.{name}: expected boolean or null")
                gates[name]["unknown" if value is None else str(value).lower()] += 1
            replay = route_fig6(Fig6GateInput(**pred["gates"]))
            if route != replay.route.value or pred["first_blocking_gate"] != replay.first_blocking_gate:
                raise ValueError(f"{rid}: route_or_blocker_differs_from_exact_fig6_replay")
        risk_counts[str(risk_gold[rid]["gold_risk_level"])] += 1
        gold_types = set(g.get("ambiguity_types") or [])
        if not gold_types <= set(AMBIGUITY_TYPES):
            raise ValueError(f"{rid}: unknown gold ambiguity type")
        if is_failed:
            predicted_types: set[str] = set()
        else:
            parsed = pred.get("parsed")
            if not isinstance(parsed, dict) or not isinstance(parsed.get("pilot_ambiguity_types"), list):
                raise ValueError(f"{rid}: parsed pilot_ambiguity_types required")
            types = parsed["pilot_ambiguity_types"]
            if len(types) != len(set(types)) or not set(types) <= set(AMBIGUITY_TYPES):
                raise ValueError(f"{rid}: invalid predicted ambiguity types")
            predicted_types = set(types)
            unresolved = parsed.get("unresolved_slots")
            if not isinstance(unresolved, list):
                raise ValueError(f"{rid}: unresolved_slots required")
            unresolved_slot_counts[str(len(unresolved))] += 1
            alternative_count += parsed.get("alternative_interpretation") is not None
            if route == "execute" and (unresolved or parsed.get("alternative_interpretation") is not None):
                raise ValueError(f"{rid}: execute with unresolved task interpretation")
            quote_support = pred.get("slot_quote_supported")
            if not isinstance(quote_support, dict):
                raise ValueError(f"{rid}: slot_quote_supported required")
            for name in SLOTS:
                if name == "actor":
                    continue
                if pred["cpc"][name]["status"] == "filled":
                    material_filled += 1
                    material_quote_supported += quote_support.get(name) is True
        ambiguity_exact += predicted_types == gold_types
        for name in predicted_types & gold_types:
            ambiguity_tp[name] += 1
        for name in predicted_types - gold_types:
            ambiguity_fp[name] += 1
        for name in gold_types - predicted_types:
            ambiguity_fn[name] += 1
        confusion[gold_route]["failed" if is_failed else route] += 1
        matched_route = route == gold_route
        route_correct += matched_route
        false_execute += route == "execute" and gold_route != "execute"
        false_refusal += route == "face_preserving_rejection" and gold_route == "execute"

        matched_all_eligible = not is_failed
        had_unsupported = False
        for name in SLOTS:
            pred_value = None if is_failed else pred_slot_value(pred["cpc"][name], rid, name)
            gold_slot = cg["gold_cpc"][name]
            eligible = cg["slot_eligibility"][name] == "eligible"
            if eligible:
                if gold_slot["status"] != "filled":
                    raise ValueError(f"{rid} cpc.{name}: eligible gold is not filled")
                gold_value = normalized(gold_slot["value"])
                slot_eligible[name] += 1
                match = pred_value == gold_value
                slot_correct[name] += match
                matched_all_eligible &= match
            elif cg["slot_eligibility"][name] == "ineligible":
                if pred_value is not None:
                    unsupported[name] += 1
                    had_unsupported = True
            else:
                raise ValueError(f"{rid} cpc.{name}: invalid gold eligibility")
        cpc_exact += matched_all_eligible
        joint_exact += matched_route and matched_all_eligible
        unsupported_records += had_unsupported

    total_eligible = sum(slot_eligible.values())
    total_correct = sum(slot_correct.values())
    micro_tp, micro_fp, micro_fn = sum(ambiguity_tp.values()), sum(ambiguity_fp.values()), sum(ambiguity_fn.values())
    micro_precision = micro_tp / (micro_tp + micro_fp) if micro_tp + micro_fp else None
    micro_recall = micro_tp / (micro_tp + micro_fn) if micro_tp + micro_fn else None
    micro_f1 = (2 * micro_tp / (2 * micro_tp + micro_fp + micro_fn)) if 2 * micro_tp + micro_fp + micro_fn else None
    return {
        "scorer": "fig6_flow_v1",
        "status": "exploratory_text_only",
        "prediction_sha256": digest(pred_path),
        "frozen_input_sha256": INPUTS,
        "records": 120,
        "failed_rows": failed,
        "route_exact": fraction(route_correct, 120),
        "route_confusion_gold_by_pred": {
            g: {p: confusion[g][p] for p in (*ROUTES, "failed")} for g in ROUTES
        },
        "false_execute_gold_nonexecute": fraction(false_execute, 44),
        "false_refusal_gold_execute": fraction(false_refusal, 76),
        "gates": {
            "gold_status": "UNSCORED_NO_INDEPENDENT_GATE_LABELS",
            "predicted_distributions": {name: dict(gates[name]) for name in GATES},
            "first_blocking_gate_descriptive": {
                name: first_blocking_gate[name] for name in (*GATES, "no_blocker", "failed")
            },
        },
        "gold_risk_distribution_descriptive": dict(risk_counts),
        "ambiguity": {
            "gold_status": "frozen_pilot_adjudicated_types",
            "exact_type_set": fraction(ambiguity_exact, 120),
            "micro_precision": micro_precision,
            "micro_recall": micro_recall,
            "micro_f1": micro_f1,
            "micro_counts": {"tp": micro_tp, "fp": micro_fp, "fn": micro_fn},
            "per_type": {
                name: {"tp": ambiguity_tp[name], "fp": ambiguity_fp[name], "fn": ambiguity_fn[name]}
                for name in AMBIGUITY_TYPES
            },
            "unresolved_slot_count_distribution_descriptive": dict(unresolved_slot_counts),
            "alternative_interpretation_rows_descriptive": alternative_count,
            "material_filled_slot_source_quote_coverage_descriptive": fraction(
                material_quote_supported, material_filled
            ),
            "failed_rows_in_denominator": failed,
        },
        "cpc": {
            "gold_eligible_filled_cells": total_eligible,
            "cell_value_accuracy": fraction(total_correct, total_eligible),
            "per_slot_value_accuracy": {
                name: fraction(slot_correct[name], slot_eligible[name]) for name in SLOTS
            },
            "record_exact_on_eligible_filled_cells": fraction(cpc_exact, 120),
            "joint_route_and_cpc_record_exact": fraction(joint_exact, 120),
            "predicted_fills_on_ineligible_gold_cells_descriptive": {
                "cells": sum(unsupported.values()),
                "ineligible_gold_cells": 120 * len(SLOTS) - total_eligible,
                "records": unsupported_records,
                "by_slot": dict(unsupported),
            },
            "normalization": "lowercase, trim/collapse whitespace, strip trailing punctuation; lists sorted",
        },
        "claim_limit": "No independent Fig. 6 gate truth, physical grounding, execution, or safety outcome is measured.",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    result = score(args.pred)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"FIG6_FLOW_V1_OK records=120 route={result['route_exact']['numerator']}/120 "
          f"cpc_cells={result['cpc']['cell_value_accuracy']['numerator']}/"
          f"{result['cpc']['cell_value_accuracy']['denominator']}")


if __name__ == "__main__":
    main()
