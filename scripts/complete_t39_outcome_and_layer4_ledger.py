"""Write frozen T39 outcome and Layer-4 computability ledgers. Does not alter T39/T41."""
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

from ambiguity_manager.evaluation.layer_failure_assignment import assign_first_observable_layer
from ambiguity_manager.model.future_task_outcome_contract_v2 import FutureTaskOutcomeV2
ROWS = ROOT / "outputs" / "pilot120_semantic_intent_judging_20260908" / "final_intent_rows.csv"
OUT_DIR = ROOT / "outputs" / "pilot120_semantic_intent_judging_20260908"
SCORING = ROOT / "pilot120_t41_complete_closure" / "scoring"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    rows = load_csv(ROWS)
    t41_by_system: dict[str, dict[str, dict[str, str]]] = {}
    for path in SCORING.glob("*_complete_row_scores.csv"):
        table = load_csv(path)
        system = table[0]["system_id"]
        t41_by_system[system] = {row["record_id"]: row for row in table}

    outcomes = []
    layer_rows = []
    for row in rows:
        t41 = t41_by_system[row["system_id"]][row["record_id"]]
        pred_cpc = t41["pred_cpc_slots"].strip()
        cpc_emitted = pred_cpc not in ("", "{}")
        cpc_exact = t41["cpc_exact"].strip().lower() == "true"
        route_correct = row["route_correct"] == "True"
        layer = assign_first_observable_layer(
            semantic_goal_correct=row["semantic_goal_correct"] == "True",
            speech_act_correct=row["speech_act_correct"] == "True",
            cpc_emitted=cpc_emitted,
            cpc_exact=cpc_exact,
            route_correct=route_correct,
        )
        outcome = FutureTaskOutcomeV2.unobserved(
            record_id=row["record_id"],
            predicted_route=row["terminal_strategy"],
            gold_route=row["gold_terminal_strategy"],
            intent_summary=None,
        ).to_dict()
        outcome["system_id"] = row["system_id"]
        outcomes.append(outcome)
        layer_rows.append({
            "record_id": row["record_id"],
            "system_id": row["system_id"],
            "semantic_goal_correct": row["semantic_goal_correct"] == "True",
            "speech_act_correct": row["speech_act_correct"] == "True",
            "route_correct": route_correct,
            "cpc_emitted": cpc_emitted,
            "cpc_exact": cpc_exact,
            "candidate_pred_count": int(t41["candidate_pred_count"]),
            "selected_pred": t41["selected_pred"].strip().lower() == "true",
            "layer": layer,
            "layer4_status": "NOT_COMPUTABLE_CPC_NEVER_EMITTED" if not cpc_emitted else ("REACHABLE" if cpc_exact and not route_correct else "NOT_LAYER4"),
        })

    out_outcomes = OUT_DIR / "t39_future_task_outcomes_unobserved.jsonl"
    out_layers = OUT_DIR / "t39_layer4_computability.json"
    if out_outcomes.exists() or out_layers.exists():
        raise ValueError("output_exists")
    out_outcomes.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in outcomes), encoding="utf-8")
    summary = {
        "claim_boundary": "Frozen T39/T41 bookkeeping only. task_success is NOT_COMPUTED. Layer 4 is NOT_COMPUTABLE because every predicted CPC frame is empty.",
        "source_hashes": {"final_intent_rows_csv": sha(ROWS)},
        "n_system_rows": len(layer_rows),
        "cpc_emitted": sum(row["cpc_emitted"] for row in layer_rows),
        "cpc_exact": sum(row["cpc_exact"] for row in layer_rows),
        "layer_counts": dict(Counter(row["layer"] for row in layer_rows)),
        "layer4_status_counts": dict(Counter(row["layer4_status"] for row in layer_rows)),
        "task_success_observed": 0,
        "rows": layer_rows,
    }
    out_layers.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "outcomes": str(out_outcomes),
        "outcomes_sha256": sha(out_outcomes),
        "layers": str(out_layers),
        "layers_sha256": sha(out_layers),
        "cpc_emitted": summary["cpc_emitted"],
        "layer4": summary["layer4_status_counts"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
