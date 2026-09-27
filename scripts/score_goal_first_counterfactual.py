#!/usr/bin/env python3
"""Score goal-first routing on frozen T39 analyses. Does not modify T39."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.schema.v2.taxonomies import CapabilityStatus, RiskLevel
from ambiguity_manager.systems.contracts import StructuredAnalysis
from ambiguity_manager.systems.routing import DeterministicRouter, POLICY_GOAL_FIRST_V1

PRED = ROOT / "review_bundles" / "pilot120_t39_20260902" / "cluster_outputs" / "R1" / "manager" / "predictions" / "full_type_risk_aware_manager.predictions.jsonl"
GOLD = ROOT / "data" / "annotations" / "pilot_120_v1" / "pilot_120_final_gold.jsonl"
INTENT = ROOT / "outputs" / "pilot120_semantic_intent_judging_20260908" / "final_intent_rows.csv"
OUT = ROOT / "outputs" / "goal_first_manager_v1_counterfactual_20260911.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["record_id"]] = row
    return rows


def analysis_from_frozen(payload: dict) -> StructuredAnalysis:
    raw = (payload.get("parsed") or {}).get("analysis") or {}
    cap = raw.get("capability_status")
    risk = raw.get("risk_level")
    speech = raw.get("speech_act")
    try:
        capability = CapabilityStatus(cap) if cap else None
    except ValueError:
        capability = None
    try:
        risk_level = RiskLevel(risk) if risk else None
    except ValueError:
        risk_level = None
    return StructuredAnalysis(
        speech_act=speech if isinstance(speech, str) else None,
        capability_status=capability,
        risk_level=risk_level,
        findings=list(raw.get("findings") or []),
        ambiguity_present=True,
    )


def main() -> None:
    if OUT.exists():
        raise ValueError("output_exists")
    gold = load_jsonl(GOLD)
    preds = load_jsonl(PRED)
    intent_rows = list(csv.DictReader(INTENT.open(encoding="utf-8", newline="")))
    sgc = {
        row["record_id"]: row["semantic_goal_correct"] == "True"
        for row in intent_rows
        if row["system_id"] == "full_type_risk_aware_manager"
    }
    router = DeterministicRouter(policy=POLICY_GOAL_FIRST_V1)
    scored = []
    for record_id, pred in preds.items():
        decision = router.route(analysis_from_frozen(pred))
        gold_route = gold[record_id]["terminal_strategy"]
        predicted = decision.recommended_strategy.value
        scored.append({
            "record_id": record_id,
            "gold_route": gold_route,
            "predicted_route": predicted,
            "matched_rule_id": decision.matched_rule_id,
            "route_correct": predicted == gold_route,
            "semantic_goal_correct": sgc[record_id],
        })
    n = len(scored)
    gold_execute = [row for row in scored if row["gold_route"] == "execute"]
    gold_reject = [row for row in scored if row["gold_route"] == "face_preserving_rejection"]
    gold_clarify = [row for row in scored if row["gold_route"] == "clarify"]
    result = {
        "system_id": "goal_first_manager_v1",
        "claim_boundary": "counterfactual reroute of frozen T39 analyses; T39 numbers unchanged; not official T39 evidence",
        "source_hashes": {"predictions": sha(PRED), "gold": sha(GOLD)},
        "n": n,
        "route_correct": sum(row["route_correct"] for row in scored),
        "predicted_route_counts": dict(Counter(row["predicted_route"] for row in scored)),
        "execute_recall_when_gold_execute": {
            "correct": sum(row["predicted_route"] == "execute" for row in gold_execute),
            "n": len(gold_execute),
        },
        "false_execute_when_gold_reject": sum(row["predicted_route"] == "execute" for row in gold_reject),
        "false_execute_when_gold_clarify": sum(row["predicted_route"] == "execute" for row in gold_clarify),
        "unnecessary_clarify_when_gold_execute": sum(row["predicted_route"] == "clarify" for row in gold_execute),
        "sgc_correct_and_gold_execute_now_executed": sum(
            row["semantic_goal_correct"] and row["gold_route"] == "execute" and row["predicted_route"] == "execute"
            for row in scored
        ),
        "frozen_t39_full_manager_route_correct": 33,
        "frozen_t39_full_manager_execute_count": 0,
        "rows": scored,
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in result if k != "rows"}, sort_keys=True))


if __name__ == "__main__":
    main()
