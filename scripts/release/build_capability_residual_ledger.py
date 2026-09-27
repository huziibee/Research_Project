"""Verify and build the 37-case residual ledger from immutable T0.7 inputs.

This reads frozen evidence and writes only the derived CSV in research/.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from lib_capability_debate_20260918 import (  # noqa: E402
    analysis_dict_from_pred,
    analysis_from_dict,
    load_jsonl_by_id,
    norm_route,
    patch_capability_in_analysis,
    prior_capability_from_pred,
    route_from_analysis,
)

BASE = ROOT / "research/pilot120"
ZIP = BASE / "artifacts/p120_full_analysis_20260923.zip"
JUDGMENTS = BASE / "capability_intervention/capability_judgments_cluster.jsonl"
SUMMARY = BASE / "capability_intervention/sprint_rescue_summary.json"
GOLD = ROOT / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl"
RISK = ROOT / "data/annotations/pilot_120_v1/pilot_120_gold_risk_official.jsonl"
OUT = BASE / "capability_intervention/residual_error_ledger.csv"
EXPECTED_SHA256 = {
    ZIP: "0305b1e9ab062876ee6ee89778cc6028d2eaf01718b7dd0295944e7d9cb81a01",
    JUDGMENTS: "e4706a5e061b6f0da90801365fc58787db102027681e83de0209622a04f649b1",
    SUMMARY: "af2acdb8fb87f2005159504d074ba94fb79b681f88d9f9c0aa7534112a7a8588",
    GOLD: "5e23ad1a92ff1873c8f039a8ce560a111dd6fb6b8ae8c11d6cf34dbfa1c360db",
}
PREDICTION_SHA256 = "e6cb2070aa56c566f955ce064775ffaac489a82962135ee69445b6e53182f258"
PREDICTION_SUFFIX = "/T0.7/predictions/goal_first_manager_v2.predictions.jsonl"
FIELDS = [
    "record_id", "gold_route", "predicted_route", "error_class",
    "predicted_capability", "gold_capability", "predicted_risk", "gold_risk",
    "diagnostic_category", "emitted_route", "gate_fix_route", "oracle_route", "case_file",
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="compare without writing")
    args = parser.parse_args()
    for path, expected in EXPECTED_SHA256.items():
        if sha256(path.read_bytes()) != expected:
            raise ValueError(f"frozen input SHA-256 mismatch: {path.relative_to(ROOT)}")

    with zipfile.ZipFile(ZIP) as archive:
        names = [name for name in archive.namelist() if name.endswith(PREDICTION_SUFFIX)]
        if len(names) != 1:
            raise ValueError("expected one repaired T0.7 prediction stream")
        raw = archive.read(names[0])
    if sha256(raw) != PREDICTION_SHA256:
        raise ValueError("repaired T0.7 prediction SHA-256 mismatch")
    preds = {row["record_id"]: row for row in (json.loads(line) for line in raw.decode("utf-8").splitlines() if line)}
    gold = load_jsonl_by_id(GOLD)
    judgments = load_jsonl_by_id(JUDGMENTS)
    risk = load_jsonl_by_id(RISK)
    if any(len(table) != 120 or set(table) != set(gold) for table in (preds, judgments, risk)):
        raise ValueError("expected the same 120 unique IDs in predictions, judgments, gold, and risk")

    counts = [0, 0, 0, 0]
    false_refuses = [0, 0, 0, 0]
    wrong_to_correct = correct_to_wrong = 0
    residual = []
    for record_id in sorted(gold):
        pred = preds[record_id]
        analysis = analysis_dict_from_pred(pred)
        if analysis is None:
            raise ValueError(f"missing parsed analysis: {record_id}")
        gold_route = norm_route(gold[record_id]["terminal_strategy"])
        predicted_cap = str(judgments[record_id]["capability_status"])
        gold_cap = str(gold[record_id]["capability_status"])
        if judgments[record_id].get("failed"):
            raise ValueError(f"failed capability judgment: {record_id}")
        routes = [
            norm_route(pred["terminal_strategy"]),
            route_from_analysis(analysis_from_dict(analysis))["goal_first_manager_v2"],
            route_from_analysis(analysis_from_dict(patch_capability_in_analysis(analysis, predicted_cap)))["goal_first_manager_v2"],
            route_from_analysis(analysis_from_dict(patch_capability_in_analysis(analysis, gold_cap)))["goal_first_manager_v2"],
        ]
        for index, route in enumerate(routes):
            counts[index] += route == gold_route
            false_refuses[index] += gold_route == "execute" and route == "refuse"
        wrong_to_correct += routes[0] != gold_route and routes[2] == gold_route
        correct_to_wrong += routes[0] == gold_route and routes[2] != gold_route
        if routes[2] == gold_route:
            continue
        predicted_risk = str(analysis.get("risk_level") or "")
        gold_risk = str(risk[record_id].get("gold_risk_level") or "")
        # Descriptive comparison only; these labels do not assign causality.
        if predicted_cap != gold_cap:
            diagnostic = "capability_disagrees_with_gold"
        elif predicted_risk and gold_risk and predicted_risk != gold_risk:
            diagnostic = "risk_disagrees_with_gold"
        else:
            diagnostic = "route_wrong_despite_matching_available_labels"
        residual.append({
            "record_id": record_id,
            "gold_route": gold_route,
            "predicted_route": routes[2],
            "error_class": f"{gold_route}->{routes[2]}",
            "predicted_capability": predicted_cap,
            "gold_capability": gold_cap,
            "predicted_risk": predicted_risk,
            "gold_risk": gold_risk,
            "diagnostic_category": diagnostic,
            "emitted_route": routes[0],
            "gate_fix_route": routes[1],
            "oracle_route": routes[3],
            "case_file": f"../cases/{record_id}.json",
        })
    if counts != [56, 57, 83, 87] or false_refuses != [39, 26, 4, 0]:
        raise ValueError(f"aggregate mismatch: exact={counts} false_refuses={false_refuses}")
    if (wrong_to_correct, correct_to_wrong, len(residual)) != (27, 0, 37):
        raise ValueError("transition or residual count mismatch")
    saved = json.loads(SUMMARY.read_text(encoding="utf-8"))
    names = ["emit_baseline_pre_codefix", "codefix_only_frozen_capability", "llm_patch_capability_current_router", "oracle_gold_capability_current_router"]
    for index, name in enumerate(names):
        if saved[name]["n_correct"] != counts[index] or saved[name]["false_refuse_on_gold_execute"] != false_refuses[index]:
            raise ValueError(f"saved summary disagrees: {name}")
        if set(saved[name]["_route_ok"]) != set(gold):
            raise ValueError(f"saved summary ID set differs: {name}")

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(residual)
    content = buffer.getvalue()
    if args.check:
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != content:
            raise ValueError("tracked residual CSV differs from frozen inputs")
    else:
        OUT.write_text(content, encoding="utf-8", newline="\n")
    print(f"CAPABILITY_LEDGER_OK residual={len(residual)} exact={counts} false_refuses={false_refuses} mode={'check' if args.check else 'build'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
